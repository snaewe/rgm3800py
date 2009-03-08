#!/usr/bin/env python
#
# These are the tests for rgm3800.py
# Copyright in 2008, 2009 by Karsten Petersen <kapet@kapet.de>
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
import math
import StringIO
import time
import unittest

import rgm3800


class Error(Exception):
  """Base exception for this module."""


class SerialMockError(Error):
  """Base exception for serial mock RGM3800 class."""

class UnexpectedDataError(Error):
  """Unexpected data was sent."""

class UnusedDataError(Error):
  """Some data wasn't received."""

class UnexpectedCallError(Error):
  """An unexpected call happened."""

class DeadlockError(Error):
  """A _recv call would deadlock."""

class MissingActionError(Error):
  """Some expected trailing actions weren't done."""


class RGM3800WithSerialMock(rgm3800.RGM3800Base):
  def __init__(self, filename):
    self._playbook = []

  def Shutdown(self):
    pass

  def _TestAddToPlaybook(self, action, data):
    if self._playbook and self._playbook[-1][0] == action:
      self._playbook[-1] = (action, self._playbook[-1][1] + data)
    else:
      self._playbook.append((action, data))

  def TestExpect(self, data):
    self._TestAddToPlaybook('send', data)

  def TestProvide(self, data):
    self._TestAddToPlaybook('recv', data)

  def _TestPrepareNextAction(self):
    self._testaction = self._playbook.pop(0)
    action = self._testaction[0]
    if action == 'send':
      self._testbuffer = StringIO.StringIO()
    elif action == 'recv':
      self._testbuffer = StringIO.StringIO(self._testaction[1])
    else:
      raise SerialMockError('unsupported action %r' % (self._testaction,))

  def _TestFinishAction(self):
    if not self._testaction:
      return
    if self._testaction[0] == 'send':
      data = self._testbuffer.getvalue()
      if data != self._testaction[1]:
        raise UnexpectedDataError('sent: %r // expected: %r'
                                  % (data, self._testaction[1]))
        # ok
    elif self._testaction[0] == 'recv':
      rest = self._testbuffer.read()
      if rest:
        raise UnusedDataError('not received: %r' % rest)
        # ok
    else:
      raise SerialMockError('unsupported action %r' % (self._testaction,))
    self._testaction = None
    del self._testbuffer
    
  def TestStart(self):
    self._testaction = None
    
  def TestFinish(self):
    self._TestFinishAction()
    if self._playbook:
      raise MissingActionError('missing actions:\n%r' % (self._playbook,))
      # ok

  def _TestCommonFunc(self, action, failmsg):
    if self._testaction:
      # Some action is active.  If it's the required type then go on with it,
      # otherwise check and close that action.
      if self._testaction[0] == action:
        return
      else:
        self._TestFinishAction()

    # If we get here then no action is currently active.

    # Are there actions remaining?
    if not self._playbook:
      raise UnexpectedCallError('no call expected, got %s' % failmsg)
      # ok

    # Get the next action.
    self._TestPrepareNextAction()

    # Is the new action of the right type?
    if self._testaction[0] != action:
      raise UnexpectedCallError('expected %s, got %s' % (self._testaction[0], failmsg))
      # ok

  def _Send(self, data):
    self._TestCommonFunc('send', 'send(%r)' % data)
    self._testbuffer.write(data)

  def _Recv(self, length=1, timeout=None):
    self._TestCommonFunc('recv', 'recv(%i, %s)' % (length, timeout))
    data = self._testbuffer.read(length)
    if (timeout is None) and (len(data) != length):
      raise DeadlockError('deadlock in _Recv')
      # ok
    return data


class SerialMockTest(unittest.TestCase):
  def setUp(self):
    self.rgm = RGM3800WithSerialMock('filename')

  def testEmptyPlaybook(self):
    self.rgm.TestStart()
    self.rgm.TestFinish()

  def testEmptyPlaybookDisallowsActions(self):
    self.rgm.TestStart()
    self.assertRaises(UnexpectedCallError,
                      self.rgm._Send, 'foo')

  def testRightOrderRightData(self):
    self.rgm.TestExpect('foo')
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.rgm._Send('foo')
    self.assertEqual('bar', self.rgm._Recv(3))
    self.rgm.TestFinish()

  def testUncalledActionInFinishRaises(self):
    self.rgm.TestExpect('foo')
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.rgm._Send('foo')
    self.assertRaises(MissingActionError,
                      self.rgm.TestFinish)

  def testWrongOrderRaises(self):
    self.rgm.TestExpect('foo')
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.assertRaises(UnexpectedCallError,
                      self.rgm._Recv, 3)

  def testRecvWithTimeout(self):
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.assertEqual('bar', self.rgm._Recv(4, 1.0))

  def testRecvDeadlockRaises(self):
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.assertRaises(DeadlockError,
                      self.rgm._Recv, 4, None)

  def testWrongDataSentRaises(self):
    self.rgm.TestExpect('foo')
    self.rgm.TestProvide('bar')
    self.rgm.TestStart()
    self.rgm._Send('foofoo')
    self.assertRaises(UnexpectedDataError,
                      self.rgm._Recv, 3)

  def testNotAllDataReceivedRaises(self):
    self.rgm.TestProvide('bar')
    self.rgm.TestExpect('foo')
    self.rgm.TestStart()
    self.rgm._Recv(1)
    self.assertRaises(UnusedDataError,
                      self.rgm._Send, 'foo')
    

class NMEATest(unittest.TestCase):
  def testCalcChecksum(self):
    self.assertEqual('00', rgm3800.NMEACalcChecksum(''))
    self.assertEqual('20', rgm3800.NMEACalcChecksum(' '))
    self.assertEqual('61', rgm3800.NMEACalcChecksum('a'))
    self.assertEqual('41', rgm3800.NMEACalcChecksum('A'))
    self.assertEqual('20', rgm3800.NMEACalcChecksum('aA'))
    self.assertEqual('00', rgm3800.NMEACalcChecksum('aa'))
    self.assertEqual('00', rgm3800.NMEACalcChecksum(chr(0)))
    self.assertEqual('FF', rgm3800.NMEACalcChecksum(chr(255)))
    self.assertEqual('30', rgm3800.NMEACalcChecksum('0' * 1001))

  def testBuildLine(self):
    self.assertEqual('$*00\r\n',
                     rgm3800.NMEABuildLine(''))
    self.assertEqual('$Hello, world!*0D\r\n',
                     rgm3800.NMEABuildLine('Hello, world!'))


def _ParseData(string):
  result = []
  for b in string.split():
    result.append(chr(int(b, 16)))
  return ''.join(result)


class RGM3800WaypointTest(unittest.TestCase):
  def testGetFormatDesc(self):
    for format in range(5):
      self.assertTrue(rgm3800.RGM3800Waypoint.GetFormatDesc(format))

  def testGetRawLength(self):
    golden = {0: 12, 1: 16, 2: 20, 3: 24, 4: 60}
    for format, expected in golden.iteritems():
      self.assertEqual(expected,
                       rgm3800.RGM3800Waypoint.GetRawLength(format))

  def testRad2Deg(self):
    def assertDegEquals(expected, rad):
      is_positive, deg, min = rgm3800.RGM3800Waypoint._Rad2Deg(rad)
      self.assertEqual(expected[0], is_positive)
      self.assertEqual(expected[1], deg)
      self.assertAlmostEqual(expected[2], min, places=2)

    # Exactly on the Equator resp. Prime Meridian.
    assertDegEquals((True, 0, 0.0), 0.0)

    # Slightly off in both directions.
    assertDegEquals((True, 0, 34.38), 0.01)
    assertDegEquals((False, 0, 34.38), -0.01)

    # On the other side of the globe.
    # TODO: Travel to Tuvalu for verification.
    assertDegEquals((True, 179, 25.62), math.pi-0.01)
    assertDegEquals((False, 180, 34.38), -math.pi-0.01)

  DATA0 = _ParseData(
      '01   0b 22 24   16 bd 72 3f   a6 28 30 3e')  # ?, UTC, Lat, Lon
  DATA1 = _ParseData(
      '01   15 0a 17   59 bc 72 3f   7e 29 30 3e '  # ?, UTC, Lat, Lon
      'bd bd 9c 42')  # Alt
  DATA2 = _ParseData(
      '01   15 0a 03   4a bc 72 3f   de 29 30 3e '  # ?, UTC, Lat, Lon
      '81 2a ac 42   fd 3e d3 3f')  # Alt, Vel
  DATA3 = _ParseData(
      '01   16 20 24   64 ED 72 3F   D5 E5 30 3E '
      'D5 2A 62 42   B2 0C 82 40   69 00 00 00')
  DATA4 = _ParseData(
      '01   16 24 29   63 ED 72 3F   F7 E5 30 3E '  # ?, UTC, Lat, Lon
      '8E 42 60 42   56 5A 8F 40   83 00 00 00 '  # Alt, Vel, Dist
      '31 C1 '  # ?
      '53 00  89 00  6D 00 '  # hdop, pdop, vdop
      '03 2A   06 28   16 24   13 27   12 24   15 21 '  # sat 1-6
      '10 15   08 1D   0F 21   07 1B   1B 1E   1A 17 '  # sat 7-12
      'A2 42 85 43')  # ?

  def testNMEARecordsFormat0(self):
    date = datetime.date(2008, 1, 1)
    golden = ('$GPGGA,113436.000,5419.6637,N,00951.3958,E,1,00,,0000.0,M,0.0,M,,0000*77\r\n'
              '$GPRMC,113436.000,A,5419.6637,N,00951.3958,E,000.00,15.15,010108,,,E*57\r\n')

    wp = rgm3800.RGM3800Waypoint(0)
    wp.Parse(self.DATA0)
    wp.SetDate(date)

    self.assertEqual(golden, wp.GetNMEARecords())

  def testNMEARecordsFormat1(self):
    date = datetime.date(1978, 2, 20)
    golden = ('$GPGGA,211023.000,5419.6249,N,00951.4069,E,1,00,,0078.4,M,0.0,M,,0000*7C\r\n'
              '$GPRMC,211023.000,A,5419.6249,N,00951.4069,E,000.00,15.15,200278,,,E*50\r\n')

    wp = rgm3800.RGM3800Waypoint(1)
    wp.Parse(self.DATA1)
    wp.SetDate(date)

    self.assertEqual(golden, wp.GetNMEARecords())

  def testNMEARecordsFormat2(self):
    date = datetime.date(2004, 2, 29)
    golden = ('$GPGGA,211003.000,5419.6219,N,00951.4118,E,1,00,,0086.1,M,0.0,M,,0000*78\r\n'
              '$GPRMC,211003.000,A,5419.6219,N,00951.4118,E,000.89,15.15,290204,,,E*53\r\n')

    wp = rgm3800.RGM3800Waypoint(2)
    wp.Parse(self.DATA2)
    wp.SetDate(date)

    self.assertEqual(golden, wp.GetNMEARecords())

  def testNMEARecordsFormat3(self):
    date = datetime.date(2000, 5, 1)
    golden = ('$GPGGA,223236.000,5422.1975,N,00953.8767,E,1,00,,0056.5,M,0.0,M,,0000*7A\r\n'
              '$GPRMC,223236.000,A,5422.1975,N,00953.8767,E,002.19,15.15,010500,,,E*5A\r\n'
              '$RTDIST,A,3,,,,105*4A\r\n')

    wp = rgm3800.RGM3800Waypoint(3)
    wp.Parse(self.DATA3)
    wp.SetDate(date)

    self.assertEqual(golden, wp.GetNMEARecords())

  def testNMEARecordsFormat4(self):
    date = datetime.date(2008, 7, 31)
    golden = ('$GPGGA,223641.000,5422.1973,N,00953.8785,E,1,12,0.8,0056.1,M,0.0,M,,0000*55\r\n'
              '$GPGSV,3,1,12,03,45,000,42,06,45,030,40,22,45,060,36,19,45,090,39*74\r\n'
              '$GPGSV,3,2,12,18,45,120,36,21,45,150,33,16,45,180,21,08,45,210,29*7E\r\n'
              '$GPGSV,3,3,12,15,45,240,33,07,45,270,27,27,45,300,30,26,45,330,23*7F\r\n'
              '$GPRMC,223641.000,A,5422.1973,N,00953.8785,E,002.42,15.15,310708,,,E*53\r\n'
              '$RTDIST,A,3,1.4,0.8,1.1,131*6E\r\n')

    wp = rgm3800.RGM3800Waypoint(4)
    wp.Parse(self.DATA4)
    wp.SetDate(date)

    self.assertEqual(golden, wp.GetNMEARecords())

  
class ParseRangeTest(unittest.TestCase):
  def testIt(self):
    self.assertEqual([0, 1, 2, 3],
                     list(rgm3800.ParseRange('', 0, 3)))
    self.assertEqual([0, 1, 2, 3, 4],
                     list(rgm3800.ParseRange('', 0, 4)))
    self.assertEqual([1],
                     list(rgm3800.ParseRange('1', 0, 3)))
    self.assertEqual([1],
                     list(rgm3800.ParseRange('1-1', 0, 3)))
    self.assertEqual([2, 3],
                     list(rgm3800.ParseRange('2-', 0, 3)))
    self.assertEqual([2, 3, 4],
                     list(rgm3800.ParseRange('2-', 0, 4)))
    self.assertEqual([0, 1],
                     list(rgm3800.ParseRange('0-1', 0, 3)))
    self.assertEqual([2, 3],
                     list(rgm3800.ParseRange('-2', 0, 3)))
    self.assertEqual(None,
                     rgm3800.ParseRange('-', 0, 3))
    self.assertEqual(None,
                     rgm3800.ParseRange('a-z', 0, 3))
    self.assertEqual(None,
                     rgm3800.ParseRange('1-0', 0, 3))
    self.assertEqual(None,
                     rgm3800.ParseRange('1-4', 0, 3))
    self.assertEqual(None,
                     rgm3800.ParseRange('1', 2, 3))
    self.assertEqual(None,
                     rgm3800.ParseRange('1', 1, 0))


class RGM3800Test(unittest.TestCase):
  def setUp(self):
    self.rgm = RGM3800WithSerialMock('filename')

  def testGetTimestamp(self):
    self.rgm.TestExpect('$PROY003*27\r\n')
    self.rgm.TestProvide('$LOG003,20071226,101221*74\r\n')
    self.rgm.TestStart()
    x = self.rgm.GetTimestamp()
    self.rgm.TestFinish()
    self.assertEqual(datetime.datetime(2007, 12, 26, 10, 12, 21), x)

  def testGetMemoryTimeframe(self):
    self.rgm.TestExpect('$PROY006*22\r\n')
    self.rgm.TestProvide('$LOG006,20071225,113436,20071226,101525*71\r\n')
    self.rgm.TestStart()
    x, y = self.rgm.GetMemoryTimeframe()
    self.rgm.TestFinish()
    self.assertEqual(datetime.datetime(2007, 12, 25, 11, 34, 36), x)
    self.assertEqual(datetime.datetime(2007, 12, 26, 10, 15, 25), y)

  def testEraseFails(self):
    self.rgm.TestExpect('$PROY109,-1*1C\r\n')
    self.rgm.TestProvide('$LOG109,0*60\r\n')
    self.rgm.TestStart()
    x = self.rgm.Erase()
    self.rgm.TestFinish()
    self.assertEqual(False, x)

  def testErase(self):
    self.rgm.TestExpect('$PROY109,-1*1C\r\n')
    self.rgm.TestProvide('$LOG109,1*61\r\n')
    for i in range(30):
      self.rgm.TestProvide('$PSRFTXTSFAM Test Report: Erase now*42\r\n')
    self.rgm.TestStart()
    x = self.rgm.Erase(msg_timeout=0.01)
    self.rgm.TestFinish()
    self.assertEqual(True, x)


if __name__ == '__main__':
  unittest.main()
