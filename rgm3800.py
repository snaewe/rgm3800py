#!/usr/bin/env python
#
# This is a program to read data off a RoyalTek RGM 3800 GPS data logger.
# Copyright in 2007, 2008 by Karsten Petersen <kapet@kapet.de>
#
# Contributions by Stephen Hildrey <steve@uptime.org.uk>
#               and Jens-Uwe Hagenah <>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
# 
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
# 
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

_SUBVERSION_ID = "$Id$"

import datetime
import errno
import getopt
import glob
import math
import os
import Queue
import re
import struct
import sys
import termios
import threading
import time


verbose = False


class Error(Exception):
  """Base exception call for this module."""


class SerialCommunicationError(Error):
  """Something is wrong about the serial communication."""


class SerialConnectionLost(SerialCommunicationError):
  """Can not send/recv anymore, serial connection is gone."""


def PrintCallInfo(func):
  """Decorator to print function with arguments and return value."""
  def _Runner(*args, **kwargs):
    all_args = ['%r' % val for val in args]
    for key, val in kwargs.iteritems():
      all_args.append('%s=%r' % (key, val))
    str_args = ', '.join(all_args)
    print >>sys.stderr, '%s(%s) <-' % (func.__name__, str_args)
    retval = func(*args, **kwargs)
    print >>sys.stderr, '%s(%s) -> %r' % (func.__name__, str_args, retval)
    return retval
  return _Runner


class _SerialMixin(object):
  """Implement buffered serial communication.

  Start:  Call constructor with filename of serial device.
  Finished:  Shutdown()
  Send data:  _Send(data)
  Recv data:  _Recv(length, timeout)
  """

  def __init__(self, filename):
    """Initialize serial communication object.

    Args:
      filename:  String, name of serial device, e.g. '/dev/ttyS0'.
    """
    self.__receiver_running = False

    # Open device and set serial communications parameters.
    # (115k baud, 8N1, no handshake, no buffering in kernel)
    self._fd = os.open(filename, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attr = termios.tcgetattr(self._fd)
    attr[0] = 0   # iflag
    attr[1] = 0   # oflag
    attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
    attr[3] = 0   # lflag
    attr[4] = termios.B115200  # ispeed
    attr[5] = termios.B115200  # ospeed
    attr[6][termios.VMIN] = 1
    attr[6][termios.VTIME] = 0
    termios.tcsetattr(self._fd, termios.TCSAFLUSH, attr)

    # Clean kernel buffers of stale data.
    termios.tcflush(self._fd, termios.TCIOFLUSH)

    # Set up communication buffers and start receiver thread.
    self.__buffer = Queue.Queue(0)
    self.__buffer2 = None

    self.__receiver = threading.Thread(target=self.__ReceiverThread)
    self.__receiver_running = True
    self.__receiver.start()

  def Shutdown(self):
    """Shut down serial communication."""
    # Notify receiver thread to stop, then wait for it.
    if self.__receiver_running:
      self.__receiver_running = False
      self.__receiver.join()

    self._Close()

  def _Close(self):
    """Flush data and close serial port file handle."""
    if self._fd:
      try:
        termios.tcflush(self._fd, termios.TCIOFLUSH)
      except termios.error:
        pass
      os.close(self._fd)
      self._fd = None

  def __ReceiverThread(self):
    """Background thread to continuously receive data and store in a buffer."""
    # I've tried select() based and direct recv() calls before but they either
    # used up more CPU time in some way or were prone to silently drop bytes.
    try:
      while self.__receiver_running:
        # Prevent us eating all CPU time.
        time.sleep(0.1)
        try:
          # Get whatever is there, if we're running every 1/10th of a second it
          # shouldn't be more than ~1.5K.
          data = os.read(self._fd, 2048)
          self.__buffer.put(data)
        except OSError, reason:
          if reason.errno == errno.EAGAIN:
            continue
          else:
            raise SerialConnectionLost
    finally:
      self.__receiver_running = False
      self._Close()

  def _Send(self, data):
    """Send some data to the device.

    Args:
      data: String, data to send.
    """
    if not self.__receiver_running:
      raise SerialConnectionLost
    os.write(self._fd, data)

  def _Recv(self, length=1, timeout=None):
    """Retrieve a specific amount of data or time out.

    This method returns if either 'length' data was received or 'timeout'
    seconds have passed.  The returned string can have less than 'length'
    bytes.  If 'timeout' is None this method will block until 'length' bytes
    can be returned.

    Args:
      length: Integer, amount of bytes to retrieve.
      timeout: Float, timeout in seconds.  Or None for no timeout.

    Returns:
      String of received data, can be empty.
    """
    # self.__buffer is the Queue feeding us data from the receiver thread.
    # self.__buffer2 is data we already got from the Queue but didn't use yet.
    starttime = time.time()
    data = ''
    while length:
      # Have we timed out?
      if timeout and time.time() > starttime + timeout:
        break

      # Fill up buffer2 by getting data from the queue.
      if not self.__buffer2:
        try:
          self.__buffer2 = self.__buffer.get_nowait()
        except Queue.Empty:
          # Don't eat all CPU!
          time.sleep(0.1)
          continue

      # Extract data from buffer2.
      if len(self.__buffer2) <= length:
        # We need all of the data in buffer2.
        data += self.__buffer2
        length -= len(self.__buffer2)
        self.__buffer2 = None
      else:
        # We only need some data in buffer2, split it out and leave the rest
        # for next time.
        data += self.__buffer2[:length]
        self.__buffer2 = self.__buffer2[length:]
        break

      # If the receiver thread isn't running anymore there will be no more
      # data.  So just bail out if we haven't finished yet.
      if length and not self.__receiver_running:
        raise SerialConnectionLost

    return data


def ParseDateTime(datestr, timestr=None):
  """Parse a date (and optional time) string and return as date[time] objects.

  Args:
    datestr: String, date spec, e.g. "20080605" for June 5th, 2008.
    timestr: String, time spec, e.g. "143500" for 14:35:00 (2:35pm).

  Returns:
    datetime.datetime instance if timestr given, else datetime.date instance.
  """
  assert len(datestr) == 8
  year  = int(datestr[0:4])
  month = int(datestr[4:6])
  day   = int(datestr[6:8])
  if timestr:
    assert len(timestr) == 6
    hour  = int(timestr[0:2])
    min   = int(timestr[2:4])
    sec   = int(timestr[4:6])
    return datetime.datetime(year, month, day, hour, min, sec)
  else:
    return datetime.date(year, month, day)


class RGM3800Waypoint(object):
  FORMATS = {
    0: {'rawlen': 12, 'desc': 'Lat,Lon'},
    1: {'rawlen': 16, 'desc': 'Lat,Lon,Alt'},
    2: {'rawlen': 20, 'desc': 'Lat,Lon,Alt,Vel'},
    3: {'rawlen': 24, 'desc': 'Lat,Lon,Alt,Vel,Dist'},
    4: {'rawlen': 60, 'desc': 'Lat,Lon,Alt,Vel,Dist,Stat'},
  }

  @classmethod
  def GetFormatDesc(cls, format):
    if format not in cls.FORMATS:
      raise Exception('Track format %i not supported!' % format)
    return cls.FORMATS[format]['desc']

  @classmethod
  def GetRawLength(cls, format):
    if format not in cls.FORMATS:
      raise Exception('Track format %i not supported!' % format)
    return cls.FORMATS[format]['rawlen']

  def __init__(self, format):
    if format not in self.FORMATS:
      raise Exception('Track format %i not supported!' % format)
    self.format = format
    self.Clear()

  def Clear(self):
    self.timestamp = None
    self.date = None
    self.lat = self.lon = 0.0
    self.alt = self.vel = 0.0
    self.dist = None
    self.sat = None
    self.hdop = self.vdop = self.pdop = None
 
  def SetDate(self, date):
    self.date = date

  def Parse(self, data):
    assert len(data) == self.GetRawLength(self.format)

    self.Clear()

    # Basic data, always logged:  UTC, latitude, longitude
    _, h, m, s, self.lat, self.lon = struct.unpack('<4B2f', data[0:12])
    self.timestamp = datetime.time(h, m, s)

    if self.format >= 1:
      # Basic data + altitude
      self.alt = struct.unpack('<f', data[12:16])[0]

    if self.format >= 2:
      # Basic data + altitude + velocity
      self.vel = struct.unpack('<f', data[16:20])[0]

    if self.format >= 3:
      # Basic data + altitude + velocity + distance travelled
      self.dist = struct.unpack('<L', data[20:24])[0]

    if self.format >= 4:
      # All above + dilution of precision + sat strengths + unknown stuff
      _ = data[24:26]  # unknown, some flags?  3d/2d lock or so?
      self.hdop, self.pdop, self.vdop = map(lambda x: x/100.0,
                                            struct.unpack('<3H', data[26:32]))
      sat = struct.unpack('<24B', data[32:56])
      self.sat = [(sat[i], sat[i+1]) for i in range(0, 24, 2)]
      _ = data[56:60]  # unknown

  RAD2DEG = 180.0/math.pi
  KMH2KNOT = 1.0/1.852

  def GetNMEARecords(self):
    data = {
      'date': self.date.strftime('%d%m%y'),
      'time': self.timestamp.strftime('%H%M%S.000')
    }

    lat = self.lat * self.RAD2DEG
    lat_deg = int(lat)
    lat_min = abs(lat-lat_deg) * 60.0
    if lat_deg >= 0:
      lat_let = 'N'
    else:
      lat_deg = abs(lat_deg)
      lat_let = 'S'
    data['lat'] = '%02i%07.4f' % (lat_deg, lat_min)
    data['lat_NS'] = lat_let

    lon = self.lon * self.RAD2DEG
    lon_deg = int(lon)
    lon_min = abs(lon-lon_deg) * 60.0
    if lon_deg >= 0:
      lon_let = 'E'
    else:
      lon_deg = abs(lon_deg)
      lon_let = 'W'
    data['lon'] = '%03i%07.4f' % (lon_deg, lon_min)
    data['lon_EW'] = lon_let

    data['alt'] = '%06.1f' % self.alt
    data['vel'] = '%06.2f' % (self.vel * self.KMH2KNOT)

    if self.dist is not None:
      data['dist'] = '%i' % self.dist
    else:
      data['dist'] = None

    if self.sat is not None:
      nsat = 0
      for sat, snr in self.sat:
        if snr:
          nsat += 1
      data['nsat'] = '%i' % nsat
    else:
      data['nsat'] = '00'

    if self.hdop is not None:
      data['hdop'] = '%01.1f' % self.hdop
      data['vdop'] = '%01.1f' % self.vdop
      data['pdop'] = '%01.1f' % self.pdop
    else:
      data['hdop'] = ''
      data['vdop'] = ''
      data['pdop'] = ''

    output = []
    output.append('GPGGA,%(time)s,%(lat)s,%(lat_NS)s,%(lon)s,%(lon_EW)s,1,%(nsat)s,%(hdop)s,%(alt)s,M,0.0,M,,0000' % data)

    if self.sat is not None:
      sat = []
      elevation = 45
      azimuth = 0
      for s in self.sat:
        sat.append('%02i,%i,%03i,%i' % (s[0], elevation, azimuth, s[1]))
        azimuth += 30
      output.append('GPGSV,3,1,12,%s,%s,%s,%s' % tuple(sat[:4]))
      output.append('GPGSV,3,2,12,%s,%s,%s,%s' % tuple(sat[4:8]))
      output.append('GPGSV,3,3,12,%s,%s,%s,%s' % tuple(sat[8:]))

    output.append('GPRMC,%(time)s,A,%(lat)s,%(lat_NS)s,%(lon)s,%(lon_EW)s,%(vel)s,15.15,%(date)s,,,E' % data)

    if data['dist']:
      output.append('RTDIST,A,3,%(pdop)s,%(hdop)s,%(vdop)s,%(dist)s' % data)

    result = []
    for o in output:
      result.append(NMEABuildLine(o))
    return ''.join(result)


def NMEACalcChecksum(msg):
  chksum = 0
  for c in msg:
    chksum ^= ord(c)
  return '%02X' % chksum


def NMEABuildLine(msg):
  return '$%s*%s\r\n' % (msg, NMEACalcChecksum(msg))


class RGM3800Base(object):
  def ShowProgress(self, msg):
    pass

  def ClearProgress(self):
    pass

  def SetShowProgress(self, show):
    pass

  def SetProgressPercent(self, percent):
    pass

  def ShowInfo(self, msg):
    pass

  def SendMessage(self, msg):
    self.ShowProgress('%s...' % msg[0:7])
    msg = NMEABuildLine(msg)
    if verbose:
      print >>sys.stderr, ">>", repr(msg)
    self._Send(msg)

  def RecvMessage(self):
    state = 'start'
    msg = ''
    while True:
      c = self._Recv(timeout=1.0)
      if c == '':
        # We didn't receive a clean message.  Drop what we got.  :-(
        return ''
      msg += c

      if state == 'start':
        if c == '$':
          state = 'start1'
          continue
        else:
          state = 'skipnl'

      elif state == 'start1':
        if c.isalpha() and c.isupper():
          state = 'start2'
          continue
        else:
          state = 'skipnl'

      elif state == 'start2':
        if c.isalpha() and c.isupper():
          state = 'start3'
          continue
        else:
          state = 'skipnl'

      elif state == 'start3':
        if c.isalpha() and c.isupper():
          state = 'line'
          continue
        else:
          state = 'skipnl'

      elif state == 'chksum':
        if c in '0123456789ABCDEF':
          state = 'chksum1'
          continue
        else:
          state = 'line'

      elif state == 'chksum1':
        if c in '0123456789ABCDEF':
          state = 'eol'
          continue
        else:
          state = 'line'

      elif state == 'eol':
        if c == '\r':
          state = 'eol1'
          continue
        else:
          state = 'line'

      elif state == 'eol1':
        if c == '\n':
          # Line completed.
          if verbose:
            print >>sys.stderr, "<<",  repr(msg)
          assert msg[0] == '$'
          assert msg[-2] == '\r'
          assert msg[-1] == '\n'
          msg = msg[1:-2]

          chksum = msg[-2:]
          msg = msg[:-3]
          shouldbe = NMEACalcChecksum(msg)
          if chksum == shouldbe:
            return msg
          else:
            # Silently ignore checksum errors and just skip the line.
            if verbose:
              print >>sys.stderr, 'checksum failed: %s != %s' % (chksum,
                                                                 shouldbe)
            state = 'start'
            msg = ''
            continue
        else:
          state = 'line'

      if state == 'line':
        if c == '*':
          state = 'chksum'
        continue

      if state == 'skipnl':
        if c == '\r':
          state = 'skipnl1'
        continue
      elif state == 'skipnl1':
        if c == '\n':
          state = 'start'
          msg = ''
        else:
          state = 'skipnl'
        continue

  def SendRecv(self, request, result=None, lines=1):
    """Send a request and receive the response.

    If no valid result is received then the request is repeated.

    Args:
      request: String, request to send.
      result: String, prefix of lines to return.
      lines: Number of lines to return.

    Returns:
      List of strings, received response.
    """
    result_lines = []
    for i in range(5):
      # Send the command.
      self.SendMessage(request)

      # Only accept a certain amount of noise.  If there is too much noise it's
      # likely communication is broken anyway.
      lines_acceptable = 20 + 5*lines

      while lines_acceptable:
        # Get a line.
        msg = self.RecvMessage()
        if not msg:
          # Got no complete line until timeout.  Finished receiving.
          break
        lines_acceptable -= 1

        if not result or msg.startswith(result):
          result_lines.append(msg)

        if lines and lines == len(result_lines):
          break

      if not result_lines:
        # Failed receiving.  Retry.
        self.ShowInfo('Timeout talking to device.  Retrying.')
        continue

      if lines and lines != len(result_lines):
        # Not enough lines received.
        self.ShowInfo('Incomplete results.  Retrying.')
        continue

      # Got a result, return it to the caller.
      return result_lines

    # If we reach this point we failed repeatedly to talk to the device.
    raise SerialCommunicationError('Can not talk to device.')

  def GetTimestamp(self):
    # There is a bug in the firmware when handling PROY003:  If the logger has
    # not made a lock on satellites yet and therefore has no idea of the time
    # it answer with LOG002 instead of LOG003!
    data = self.SendRecv('PROY003', lines=1)
    if not data[0].startswith('LOG003,'):
      return None
    self.ClearProgress()
    data = data[0].split(',')
    # LOG003,20071226,101221
    return ParseDateTime(data[1], data[2])

  def GetMemoryTimeframe(self):
    data = self.SendRecv('PROY006', result='LOG006,')
    _, fromdate, fromtime, todate, totime = data[0].split(',')
    return ParseDateTime(fromdate, fromtime), ParseDateTime(todate, totime)

  def SetGPSMouse(self, enabled):
    if enabled:
      i = 1
    else:
      i = 0
    data = self.SendRecv('PROY103,0,%i' % i, result='LOG103')
    self.ClearProgress()
    _, result = data[0].split(',')
    return result == '1'

  def SetInterval(self, interval):
    info = self.GetInfo()
    format = info[0]
    memoryfull = info[3]
    data = self.SendRecv('PROY104,0,%i,%i,%i' % (interval,format,memoryfull),
                         result='LOG104')
    self.ClearProgress()
    _, result = data[0].split(',')
    return result == '1'

  def SetFormat(self, format):
    info = self.GetInfo()
    memoryfull = info[3]
    interval = info[5]
    data = self.SendRecv('PROY104,0,%i,%i,%i' % (interval,format,memoryfull),
                         result='LOG104')
    self.ClearProgress()
    _, result = data[0].split(',')
    return result == '1'

  def SetMemoryFull(self, memoryfull):
    info = self.GetInfo()
    format = info[0]
    interval = info[5]
    memoryfull = ['overwrite', 'stop'].index(memoryfull)
    data = self.SendRecv('PROY104,0,%i,%i,%i' % (interval,format,memoryfull),
                         result='LOG104')
    self.ClearProgress()
    _, result = data[0].split(',')
    return result == '1'
 
  def GetInfo(self):
    msg = self.SendRecv('PROY108', result='LOG108,')
    data = msg[0].split(',')[1:]
    # data type, ?, ?, memory full, ?, interval, ?, #tracks, #waypoints in last track
    return map(int, data)

  def GetMemoryInfo(self):
    msg = self.SendRecv('PROY100', result='LOG100,')
    data = msg[0].split(',')[1:]
    # total memory, sector size, #sectors
    return map(int, data)

  def GetTrackInfo(self, number):
    msg = self.SendRecv('PROY101,%i' % number, result='LOG101,')
    data = msg[0].split(',')[1:]
    date = ParseDateTime(data[0])
    data = [date] + map(int, data[1:])
    # date, data type, #waypoints, memory address
    return data

  def GetAllTrackInfo(self):
    _, _, _, _, _, _, _, tracks, _ = self.GetInfo()
    for i in range(tracks):
      data = self.GetTrackInfo(i)

  def _RetrieveWaypoints(self, address, format, n):
    waypoint_len = RGM3800Waypoint.GetRawLength(format)
    retries = 5
    wps = []
    while len(wps) != n:
      if retries <= 0:
        raise SerialCommunicationError
      self.SendMessage('PROY102,%i,%i,%i' % (address, format, n))
      retries -= 1

      noise = 0
      wps = []
      while len(wps) != n:
        msg = self.RecvMessage()
        if not msg:
          break
        if noise > 100:
          raise SerialCommunicationError('too much noise')
        if not msg.startswith('LOG102,'):
          noise += 1
          continue
        try:
          part, length = struct.unpack('<HB', msg[7:10])
        except struct.error:
          # Probably a broken line.  Ignore.  Several of these means the
          # communication is broken.
          noise += 20
          continue
        msg = msg[10:]
        if len(msg) % waypoint_len != 0:
          # Silently ignore broken lines, retransmit will fix this.
          continue
        while len(msg):
          data = msg[:waypoint_len]
          msg = msg[waypoint_len:]

          wp = RGM3800Waypoint(format)
          wp.Parse(data)
          wps.append(wp)
    return wps

  def GetFirstLastWaypoints(self, number):
    date, format, number, address = self.GetTrackInfo(number)

    waypoint_len = RGM3800Waypoint.GetRawLength(format)

    first_wp = self._RetrieveWaypoints(address, format, 1)[0]
    address += waypoint_len * (number - 1)
    last_wp = self._RetrieveWaypoints(address, format, 1)[0]

    first_wp.SetDate(date)
    last_wp.SetDate(date)
    return first_wp, last_wp

  def GetWaypoints(self, number):
    date, format, number, address = self.GetTrackInfo(number)

    waypoint_len = RGM3800Waypoint.GetRawLength(format)
    bytes_per_request = 4800
    waypoints_per_request = bytes_per_request / waypoint_len

    packages, rest = divmod(number, waypoints_per_request)
    if rest:
      packages += 1

    waypoints = []
    self.SetProgressPercent(0)
    _number = number
    for i in range(packages):
      n = min(waypoints_per_request, _number)
      wps = self._RetrieveWaypoints(address, format, n)
      _number -= n
      address += n * waypoint_len
      waypoints.extend(wps)
      self.SetProgressPercent((len(waypoints) * 100) / number)

    for wp in waypoints:
      wp.SetDate(date)

    self.SetProgressPercent(None)
    return waypoints


class RGM3800(RGM3800Base, _SerialMixin):
  def __init__(self, device):
    super(RGM3800, self).__init__(device)
    self.progress_dash = 0
    self.progress_percent = None
    self.show_progress = True

  def SetShowProgress(self, show):
    self.show_progress = show

  def SetProgressPercent(self, percent):
    self.progress_percent = percent

  def ShowProgress(self, msg):
    if self.show_progress:
      head = '/-\|'[self.progress_dash]
      self.progress_dash = (self.progress_dash + 1) & 3
      if self.progress_percent is not None:
        head += ' %i%%' % self.progress_percent
      sys.stderr.write('[%s %s]\r' % (head, msg))
      sys.stderr.flush()

  def ClearProgress(self):
    if self.show_progress:
      sys.stderr.write(' ' * 40 + '\r')
      sys.stderr.flush()

  def ShowInfo(self, msg):
    sys.stderr.write('[%s]\n' % msg)


def DoInfo(rgm, args):
  if len(args) != 0:
    return DoHelp(rgm, args)

  info = rgm.GetInfo()
  config_format, _, _, memoryfull, _, interval, _, tracks, _ = info
  format_string = RGM3800Waypoint.GetFormatDesc(config_format)
  if memoryfull == 0:
    memoryfull_string = 'overwrite oldest sector'
  elif memoryfull == 1:
    memoryfull_string = 'stop logging'
  else:
    memoryfull_string = '[unknown setting %i]' % memoryfull

  timestamp = rgm.GetTimestamp()

  memory, _, _, _ = rgm.GetMemoryInfo()

  data = rgm.SendRecv('PROY005', lines=5)
  version = data[1].split(']', 1)[1]

  memory_from, memory_to = rgm.GetMemoryTimeframe()

  total_size = 0
  total_waypoints = 0
  rgm.SetProgressPercent(0)
  for i in range(tracks):
    _, format, waypoints, _ = rgm.GetTrackInfo(i)
    ilen = RGM3800Waypoint.GetRawLength(format)
    total_size += ilen * waypoints
    total_waypoints += waypoints
    rgm.SetProgressPercent(i*100/(tracks-1))
  rgm.SetProgressPercent(None)

  print '### Device ###'
  print 'Firmware version: %s' % version
  print 'Total memory    : %i KB' % (memory // 1024)
  if timestamp:
    print 'Current UTC time: %s' % timestamp
  print
  print '### Configuration ###'
  print 'Logging format  : %s' % format_string
  print 'Logging interval: %i seconds' % interval
  print 'If memory full  : %s' % memoryfull_string
  print
  waypoints_per_hour = 3600.0/interval
  bytes_per_hour = waypoints_per_hour * RGM3800Waypoint.GetRawLength(config_format)
  hours_to_memoryfull = (memory - total_size) / bytes_per_hour
  print '=> %i waypoints per hour' % waypoints_per_hour
  print '   %i bytes per hour' % bytes_per_hour
  print '   %i days %i hours until memory full' % (hours_to_memoryfull / 24, hours_to_memoryfull % 24)
  print
  print '### Usage ###'
  print 'Total waypoints : %i' % total_waypoints
  print 'Number of tracks: %i' % tracks
  print 'Oldest waypoint : %s' % memory_from
  print 'Newest waypoint : %s' % memory_to
  print 'Memory in use   : %.2f%%' % (total_size*100.00/memory)

  return 0


def DoDate(rgm, args):
  if len(args) != 0:
    return DoHelp(rgm, args)

  timestamp = rgm.GetTimestamp()
  if timestamp:
    print timestamp.strftime('%m%d%H%M%Y')
  else:
    print 'Date and time not available yet.'


def ParseRange(arg, min_, max_):
  """Parse a range description and assert a range.

  Supported formats:
    "":    min_ .. max_
    "x":   x .. x
    "x-":  x .. max_
    "x-y": x .. y
    "-z:   max_-z+1 .. max_  ("The last z entries.")

  Args:
    arg: String, input argument.
    min_: Integer, minimum value for start and end of range.
    max_: Integer, maximum value for start and end of range.

  Returns:
    None if unable to parse arg or iterator for the requested range,
    yielding integers.
  """
  start = min_
  end = max_

  if arg:
    arg_match = re.match(r'^(?:(\d+)|(\d+)-|-(\d+)|(\d+)-(\d+))$', arg)
    if not arg_match:
      return None
    arg = arg_match.groups()
    if arg[0] != None:
      # "x"
      start = end = int(arg[0])
    elif arg[1] != None:
      # "x-"
      start = int(arg[1])
    elif arg[2] != None:
      # "-z"
      start = max_ - int(arg[2]) + 1
    else:
      # "x-y"
      start = int(arg[3])
      end = int(arg[4])

  if min_ <= start <= end <= max_:
    return xrange(start, end + 1)
  else:
    return None

  
def DoList(rgm, args):
  if len(args) > 1:
    return DoHelp(rgm, args)

  info = rgm.GetInfo()
  _, _, _, _, _, _, _, tracks, _ = info

  range_iter = ParseRange(len(args) and args[0] or '', 0, tracks-1)
  if not range_iter:
    return DoHelp(rgm, args)

  for i in range_iter:
    date, format, waypoints, address = rgm.GetTrackInfo(i)
    format_string = RGM3800Waypoint.GetFormatDesc(format)
    first_wp, last_wp = rgm.GetFirstLastWaypoints(i)
    output = 'Track %3i:  %s (%s - %s), %5i waypoints (%s)' % (i, date,
        first_wp.timestamp, last_wp.timestamp, waypoints, format_string)
    if last_wp.dist:
      output += ', %i meter' % last_wp.dist
    print output


def DoTrack(rgm, args):
  if len(args) != 1:
    return DoHelp(rgm, args)

  info = rgm.GetInfo()
  _, _, _, _, _, _, _, tracks, _ = info

  range_iter = ParseRange(args[0], 0, tracks-1)
  if not range_iter:
    return DoHelp(rgm, args)

  for i in range_iter:
    waypoints = rgm.GetWaypoints(i)
    for wp in waypoints:
      sys.stdout.write(wp.GetNMEARecords())

  return 0


def DoGMouse(rgm, args):
  if len(args) != 1 or args[0] not in ('on', 'off'):
    return DoHelp(rgm, args)
  state = ['off', 'on'].index(args[0])
  if rgm.SetGPSMouse(state):
    print 'OK'
  else:
    print 'Failed.  Maybe your firmware does not support this interval?'
  return 0


def DoDump(rgm, args):
  if args:
    return DoHelp(rgm, args)
  try:
    while True:
      msg = rgm.RecvMessage()
      if not msg:
        continue
      print msg
  except KeyboardInterrupt:
    pass
  return 0


def DoInterval(rgm, args):
  if not ((len(args) == 1) and (1 <= int(args[0]) <= 60)):
    return DoHelp(rgm, args)
  interval = int(args[0])
  if rgm.SetInterval(interval):
    print 'OK'
  else:
    print 'Failed.  Maybe your firmware does not support this interval?'
  return 0


def DoFormat(rgm, args):
  if not ((len(args) == 1) and (0 <= int(args[0]) <= 3)):
    return DoHelp(rgm,args)
  format = int(args[0])
  if rgm.SetFormat(format):
    print 'OK'
  else:
    print 'Failed.  Maybe your firmware does not support this mode?'
  return 0


def DoMemoryFull(rgm, args):
  if len(args) != 1 or args[0] not in ('overwrite', 'stop'):
    return DoHelp(rgm, args)
  if rgm.SetMemoryFull(args[0]):
    print 'OK'
  else:
    print 'Failed.  Maybe your firmware does not support this mode?'
  return 0


def DoHelp(rgm, args):
  print 'Usage: %s <GLOBAL OPTIONS> <COMMAND> <COMMAND OPTIONS>' % sys.argv[0]
  print
  print 'GLOBAL OPTIONS:'
  print '    -d <dev>, --device=<dev>        Serial device to use'
  print '    -v, --verbose                   Show serial communication details'
  print
  print 'COMMANDS:'
  print '    help                            This help'
  print '    info                            Show some info about the device'
  print '    date                            date -u `%s date`' % sys.argv[0]
  print '    list [<range>]                  List tracks [in range]'
  print '    track <range>                   Print waypoints as NMEA records'
  print '    interval <secs>                 Set interval between waypoints (1 <= i <= 60)'
  print '    memoryfull <overwrite|stop>     Set memory full behaviour'
  print '    format <x>                      Set what data is logged'
  print '    gmouse <on|off>                 Turn GPS mouse on/off'
  print '    dump                            Continuously read+dump data from device'
  print
  print 'Known formats:'
  for i in range(10):
    try:
      size = RGM3800Waypoint.GetRawLength(i)
      desc = RGM3800Waypoint.GetFormatDesc(i)
      print '    %i:  %i bytes/waypoint;  %s' % (i, size, desc)
    except:
      break
  print
  print '<range> for list/track:'
  print '    8                               8th track only'
  print '    5-                              5th to last track'
  print '    7-9                             7th to 9th track'
  print '    -2                              last two tracks'
  print
  print _SUBVERSION_ID
  return 0


commands = {
  'info': DoInfo,
  'date': DoDate,
  'list': DoList,
  'track': DoTrack,
  'interval': DoInterval,
  'format': DoFormat,
  'memoryfull': DoMemoryFull,
  'gmouse': DoGMouse,
  'dump': DoDump,
  'help': DoHelp,
}


def main(argv):
  device = None

  options, args = getopt.getopt(argv[1:], 'hd:v', ['help', 'device=', 'verbose'])
  for key, value in options:
    if key in ('-h', '--help'):
	return DoHelp(None, [])
    elif key in ('-d', '--device'):
      device = value
    elif key in ('-v', '--verbose'):
      global verbose
      verbose = True
    else:
      assert False, 'Option %s not implemented.' % key

  if not device:
    devices = glob.glob('/dev/cu.PL2303-*')
    if len(devices) == 0:
      print >>sys.stderr, 'No PL2303 serial device found.  Use --device=...'
      return -1
    if len(devices) > 1:
      print >>sys.stderr, 'Multiple PL2303 serial devices found.  Use --device=...'
      return -1
    device = devices[0]

  if len(args) == 0:
    args = ['help']
  command = args[0]
  args = args[1:]
  if command not in commands:
    command = 'help'
  func = commands[command]

  rgm = RGM3800(device)
  if verbose:
    rgm.SetShowProgress(False)
  try:
    retval = func(rgm, args)
  finally:
    rgm.Shutdown()

  return retval


if __name__ == '__main__':
  sys.exit(main(sys.argv))
