(*	
	rgm3800_Setup.applescript
	rgm3800_Setup

	Contains and relies on the python-script "rgm3800.py"
	Available here: http://code.google.com/p/rgm3800py/
	Copyright in 2007, 2008, 2009 by Karsten Petersen <kapet@kapet.de>
	
	Relies on the "Prolific PL2303 USB serial adapter driver for Mac OS X"
	Available here: http://osx-pl2303.sourceforge.net/
	Copyright 2006, 2007 BJA Electronics Amstelveen, Nederland, B.J. Arnoldus 
	
	This ApplescriptStudio App:
	Created by Niels Volkmann <softwaresachen@gmx.de> on 20.06.09.
	Copyright 2009 Niels Volkmann. All rights reserved.
	
	
	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.
 
	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.
 
	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <http://www.gnu.org/licenses/>.

*)

property format : {"Lat,Lon", "Lat,Lon,Alt", "Lat,Lon,Alt,Vel", "Lat,Lon,Alt,Vel,Dist", "Lat,Lon,Alt,Vel,Dist,Stat"}
property formatx : {"Lat,Lon", "Lat,Lon,Alt", "Lat,Lon,Alt,Vel", "Lat,Lon,Alt,Vel,Dist", "Lat,Lon,Alt,Vel,Dist,Stat"}
property speicher_voll_verhalten : {"stop", "over"}

--property speicher_voll_verhaltenx : {"überschreiben", "stoppen"}
property speicher_voll_verhaltenx : {"", ""}
property firmware : ""
property output : ""
property rgm3800path : ""
property mainwindow : "rgm3800"

--PRÜFEN OB NOCH GEBRAUCHT
--property einstellungen : "Einstellungen"

property trackliste : ""
property speicher : ""
property currentTrack : ""
property selectedTracks : ""
property savefolder : "/"
property savetemp : ""
property AktuellerTrack : ""
property daten_vorhanden : "nein"

-- Trackliste Delimiters
property substringBegin : "Track"
property substringEnd : ":  "
property substringDateBegin : " ("
property originalDelimiters : ""

property tracknummer : ""
property trackentfernung : ""
property theItems : ""
property skriptversion : ""
property gpsbabelpfad : ""



on awake from nib theObject
	if (name of theObject is mainwindow) then
		
		--Tab verstellen
		tell tab view "Auswahl" of window mainwindow
			set the current tab view item to tab view item "Tracks_laden"
		end tell
		
		--Pfad zum Bundle festellen
		set folderPath to POSIX path of ((path to me) as text)
		
		--Pfad zum Skript festlegen
		set rgm3800path to quoted form of (folderPath & "Contents/Resources/rgm3800.py")
		
		--Skriptversion festellen
		set skriptversion to do shell script rgm3800path & " version"
		set contents of text field "skriptversion" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to skriptversion
		
		set contents of text field "savefolder" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to savefolder
		delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
	end if
end awake from nib


on clicked theObject
	
	
	-- Speicherordner auswählen
	if (name of theObject is "Speicherordner") then
		try
			set savetemp to choose folder default location (path to desktop)
			set savefolder to POSIX path of savetemp
			set contents of text field "savefolder" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to savefolder
		end try
	end if
	
	
	-- Löschen der Tracks
	if (name of theObject is "Loeschen") then
		set buttonabfrage to button returned of (display dialog (localized string "DELETE_TRACKS" from table "Localizable") buttons {(localized string "CANCEL" from table "Localizable"), (localized string "OK" from table "Localizable")} default button 1)
		if buttonabfrage is equal to (localized string "OK" from table "Localizable") then
			try
				tell progress indicator "Indikator2" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to start
				do shell script "echo y |" & rgm3800path & " erase all"
			on error errMsg number errNr
				tell progress indicator "Indikator2" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
				display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
			end try
			tell progress indicator "Indikator2" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
		else
			return
		end if
	end if
	
	
	-- Firmware Version anzeigen
	if (name of theObject is "Firmware") then
		try
			tell progress indicator "Indikator4" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
			if output is equal to "" then
				try
					set output to do shell script rgm3800path & " info" without altering line endings
					set firmware to do shell script "echo " & quoted form of output & "|grep \"Firmware\" | cut -c 19-50 | sed 's/ //'"
				on error errMsg number errNr
					tell progress indicator "Indikator4" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
					display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
				end try
			else
				set firmware to do shell script "echo " & quoted form of output & "|grep \"Firmware\" | cut -c 19-50 | sed 's/ //'"
			end if
			tell progress indicator "Indikator4" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
			if output is not equal to "" then
				display dialog firmware buttons {(localized string "OK" from table "Localizable")} default button 1
			end if
		on error errMsg number errNr
			tell progress indicator "Indikator4" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
			display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
		end try
	end if
	
	
	--Sichern der vorgenommenen Einstellungen im RGM3800
	if (name of theObject is "Sichern") then
		
		-- Abfrage ob die derzeitigen Einstellungen vorliegen
		if (daten_vorhanden is equal to "ja") then
			-- Abfrage ob im Intervall-Feld ein Wert hinterlegt ist
			if (contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow is not equal to "") then
				--Ändern des Logging-Interval
				try
					tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
					try
						set intervaltemp to contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow as real
					on error errMsg number errNr
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
						display dialog (localized string "ONLY_NUMBERS" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
						set contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to interval
					end try
					set intervaltemp to contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
					
					try
						do shell script rgm3800path & " interval " & intervaltemp
						delay 1
					on error errMsg number errNr
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
						display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
						return
					end try
					
					
					--Ändernd des Speicher voll Verhaltens
					set speicher_voll_verhalten_temp to title of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
					if (speicher_voll_verhalten_temp is equal to (localized string "OVERWRITE" from table "Localizable")) then
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
						do shell script rgm3800path & " memoryfull overwrite"
						delay 1
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
					else
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
						do shell script rgm3800path & " memoryfull stop"
						delay 1
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
					end if
					
					
					--Ändern des Logging-Formats
					set format to title of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
					
					if (format is equal to "Lat,Lon,Alt,Vel,Dist,Stat") then
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
						do shell script rgm3800path & " format 4"
						delay 1
						tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
					else
						if (format is equal to "Lat,Lon,Alt,Vel,Dist") then
							tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
							do shell script rgm3800path & " format 3"
							delay 1
							tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
						else
							tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
							if (format is equal to "Lat,Lon,Alt,Vel") then
								do shell script rgm3800path & " format 2"
								delay 1
								tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
							else
								tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
								if (format is equal to "Lat,Lon,Alt") then
									do shell script rgm3800path & " format 1"
									delay 1
									tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
								else
									tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
									do shell script rgm3800path & " format 0"
									delay 1
									tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
								end if
							end if
						end if
					end if
				on error errMsg number errNr
					tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
					display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
				end try
				tell progress indicator "Indikator3" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
			else
				display dialog (localized string "INTERVAL" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
			end if
		else
			display dialog (localized string "GET_LOGGER_INFO" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
		end if
	end if
	
	
	-- Abrufen der Trackliste des GPS-Loggers
	if (name of theObject is "Trackliste") then
		tell progress indicator "trackwahlindikator" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to start
		try
			try
				-- Verarbeitet Feld ggf löschen
				if contents of text field "Verarbeitet" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow is not "" then
					delete contents of text field "Verarbeitet" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow
				end if
			end try
			
			-- Abfragen ob Trackliste schon geladen
			if trackliste is "" then
				set trackliste to do shell script rgm3800path & " list" without altering line endings
				set originalDelimiters to AppleScript's text item delimiters
				set AppleScript's text item delimiters to {substringBegin}
				set theItems to text items 2 thru (count of text items of trackliste) of trackliste
				set AppleScript's text item delimiters to originalDelimiters
			end if
			tell progress indicator "trackwahlindikator" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
			set selectedTracks to choose from list theItems with prompt (localized string "WHICH_TRACKS" from table "Localizable") OK button name (localized string "CHOOSE" from table "Localizable") with multiple selections allowed
			
			-- Anzahl gewählter Tracks zeigen
			if ((count of text items of selectedTracks) of selectedTracks) is equal to 1 then
				try
					set contents of text field "Anzahl_Tracks_gewaehlt" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to (((count of text items of selectedTracks) of selectedTracks) as string) & (localized string "TRACK_CHOSEN" from table "Localizable")
				end try
			else
				try
					set contents of text field "Anzahl_Tracks_gewaehlt" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to (((count of text items of selectedTracks) of selectedTracks) as string) & (localized string "TRACKS_CHOSEN" from table "Localizable")
				end try
			end if
			
		on error errMsg number errNr
			tell progress indicator "trackwahlindikator" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
			set AppleScript's text item delimiters to originalDelimiters
		end try
		tell progress indicator "trackwahlindikator" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
	end if
	
	
	-- Laden der gewählten Tracks
	if (name of theObject is "Tracks_laden_button") then
		if trackliste is not "" then
			tell progress indicator "Indikator5" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to start
			try
				set AktuellerTrack to 1
				set AnzahlTracks to ((count of text items of selectedTracks) of selectedTracks)
				
				--Jeden gewählten Track verarbeiten
				repeat with currentTrack in selectedTracks
					set trackentfernung to ""
					set trackformattemp to do shell script " echo " & quoted form of currentTrack & " | awk '{printf $8}'" --| sed -e 's/(//' -e 's/)//'")
					if trackformattemp contains "Dist" then
						set trackentfernung to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $9}'"
						set trackformat to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $8}' | sed -e 's/(//' -e 's/),//'"
					else
						set trackformat to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $8}' | sed -e 's/(//' -e 's/)//'"
					end if
					set tracknummer to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $1}' | sed 's/://'"
					set trackdatum to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $2}'"
					set trackzeitanfang to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $3}' | sed -e 's/(//' -e 's/:/_/g'"
					set trackzeitende to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $5}' | sed -e 's/),//' -e 's/:/_/g'"
					set trackwegpunkte to do shell script "echo " & quoted form of currentTrack & " | awk '{printf $6}'"
					set fileNAME to trackdatum & " " & "(" & trackzeitanfang & "-" & trackzeitende & ")" & " " & trackwegpunkte & (localized string "WAYPOINTS" from table "Localizable") & " " & "(" & trackformat & ")"
					set contents of text field "Verarbeitet" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to (localized string "PROCESSING_TRACKS_1" from table "Localizable") & AktuellerTrack & (localized string "PROCESSING_TRACKS_2" from table "Localizable") & AnzahlTracks
					delay 1
					do shell script rgm3800path & " trackx " & tracknummer & " > " & quoted form of savefolder & quoted form of fileNAME & ".gpx"
					set AktuellerTrack to AktuellerTrack + 1
				end repeat
				
				-- Anzahl verarbeiteter Tracks zeigen
				if AnzahlTracks is equal to 1 then
					try
						set contents of text field "Verarbeitet" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to (AnzahlTracks as string) & (localized string "PROCESSED_TRACK" from table "Localizable")
					end try
				else
					try
						set contents of text field "Verarbeitet" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to (AnzahlTracks as string) & (localized string "PROCESSED_TRACKS" from table "Localizable")
					end try
				end if
				
				-- ggf. per Growl benachrichtigen
				tell application "System Events" to set growlstatus to exists application process "GrowlHelperApp"
				if growlstatus then
					set growl_tracks_processed to (localized string "GROWL_TRACKS_PROCESSED" from table "Localizable")
					tell application "GrowlHelperApp"
						register as application "rgm3800" all notifications {"Processing_status"} default notifications {"Processing_status"} icon of application "rgm3800"
						notify with name "Processing_status" title "rgm3800" description "" & growl_tracks_processed application name "rgm3800"
					end tell
				end if
			on error errMsg number errNr
				log errNr
				log errMsg
				tell progress indicator "Indikator5" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
				display dialog (localized string "PROCESSING_ERROR" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
			end try
			tell progress indicator "Indikator5" of box "Trackbox" of tab view item "Tracks_laden" of tab view "Auswahl" of window mainwindow to stop
		else
			display dialog (localized string "NO_TRACKS_CHOSEN" from table "Localizable") buttons {"Ok"} default button 1
		end if
	end if
	
	
	-- Abfragen des GPS-Loggers
	if (name of theObject is "Logger abfragen") then
		set speicher_voll_verhaltenx to {(localized string "OVERWRITE" from table "Localizable"), (localized string "STOP" from table "Localizable")}
		tell progress indicator "Indikator" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to start
		try
			set daten_vorhanden to "ja"
			set output to do shell script rgm3800path & " info" without altering line endings
			tell window mainwindow
				set contents of text field "output" of drawer "Drawer" to output
			end tell
			set interval to do shell script "echo " & quoted form of output & " |grep \"Logging interval\" | cut -c 19-20 | sed 's/ //'"
			set contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to interval
			set firmware to do shell script "echo " & quoted form of output & " |grep \"Firmware\" | cut -c 19-50 | sed 's/ //'"
			set speicher to do shell script "echo " & quoted form of output & " |grep \"Memory in use\" | cut -c 18-23 | sed 's/\\./\\,/' | sed 's/%//'"
			set contents of text field "Speicherfreibox" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to (speicher) & " %" -- as text
			set zeit to do shell script "echo " & quoted form of output & " |grep \"Current UTC time\" | cut -c 30-37"
			
			-- Prüfen ob Zeit verfügbar
			if zeit is equal to "" then
				set contents of text field "Zeitbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to (localized string "NO_DATE_OR_TIME" from table "Localizable")
			else
				set contents of text field "Zeitbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to zeit
			end if
			
			set datum_tag to do shell script "echo " & quoted form of output & " |grep \"Current UTC time\" | cut -c 27-28"
			set datum_monat to do shell script "echo " & quoted form of output & " |grep \"Current UTC time\" | cut -c 24-25"
			set datum_jahr to do shell script "echo " & quoted form of output & " |grep \"Current UTC time\" | cut -c 19-22"
			
			-- Prüfen ob Datum verfügbar
			if datum_tag is equal to "" then
				set contents of text field "Datumbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to (localized string "NO_DATE_OR_TIME" from table "Localizable")
			else
				set datum to datum_tag & "." & datum_monat & "." & datum_jahr
				set contents of text field "Datumbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to datum
			end if
			
			set format to do shell script "echo " & quoted form of output & " |grep \"Logging format\" | cut -c 19-45"
			set speicher_voll_verhalten to do shell script "echo " & quoted form of output & " |grep \"If memory full\"|cut -c 19-22"
			set restdauer_tage to do shell script "echo " & quoted form of output & " |grep \"until memory full\" | awk {print'$1'}"
			set restdauer_stunden to do shell script "echo " & quoted form of output & " |grep \"until memory full\" | awk {print'$3'}"
			
			--unterscheiden ob restdauer_tage =1 oder !=1
			if restdauer_tage is equal to "1" then
				set contents of text field "Restdauerbox" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to (restdauer_tage & (localized string "DAY" from table "Localizable") & restdauer_stunden & (localized string "HOUR" from table "Localizable"))
			else
				set contents of text field "Restdauerbox" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to (restdauer_tage & (localized string "DAYS" from table "Localizable") & restdauer_stunden & (localized string "HOUR" from table "Localizable"))
			end if
			set trackanzahl to do shell script "echo " & quoted form of output & "| grep \"Number of tracks\" | awk {'print $4'}"
			set contents of text field "Tracks" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to trackanzahl
			
			-- speicher_voll_button mit inhalt füllen
			if (speicher_voll_verhalten is equal to "stop") then
				delete every menu item of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
				repeat with i in my speicher_voll_verhaltenx
					make new menu item at the end of menu items of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
				end repeat
				set current menu item of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 2 of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
			else
				delete every menu item of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
				repeat with i in my speicher_voll_verhaltenx
					make new menu item at the end of menu items of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
				end repeat
				set current menu item of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 1 of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
			end if
			
			-- format popup button mit Inhalt füllen
			if (format is equal to "Lat,Lon,Alt,Vel,Dist,Stat") then
				delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
				repeat with i in my formatx
					make new menu item at the end of menu items of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
				end repeat
				set current menu item of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 5 of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
			else
				if (format is equal to "Lat,Lon,Alt,Vel,Dist") then
					delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
					repeat with i in my formatx
						make new menu item at the end of menu items of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
					end repeat
					set current menu item of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 4 of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
				else
					if (format is equal to "Lat,Lon,Alt,Vel") then
						delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
						repeat with i in my formatx
							make new menu item at the end of menu items of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
						end repeat
						set current menu item of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 3 of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
					else
						if (format is equal to "Lat,Lon,Alt") then
							delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
							repeat with i in my formatx
								make new menu item at the end of menu items of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
							end repeat
							set current menu item of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 2 of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
						else
							delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
							repeat with i in my formatx
								make new menu item at the end of menu items of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow with properties {title:i, enabled:true}
							end repeat
							set current menu item of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to menu item 1 of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
						end if
					end if
				end if
			end if
			
			-- Felder im Fehlerfall leeren	
		on error errMsg number errNr
			set daten_vorhanden to "nein"
			set leer to "" as string
			set contents of text field "Interval" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Zeitbox" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Datumbox" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Speicherfreibox" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Restdauerbox" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Tracks" of box "Speichernutzung" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Zeitbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			set contents of text field "Datumbox" of box "Zeit und Datum Box" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to leer
			delete every menu item of menu of popup button "format" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
			delete every menu item of menu of popup button "speicher_voll_button" of box "Einstellungen" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow
			tell progress indicator "Indikator" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
			display dialog (localized string "LOGGER_NOT_FOUND" from table "Localizable") buttons {(localized string "OK" from table "Localizable")} default button 1
		end try
		tell progress indicator "Indikator" of tab view item "Einstellungen" of tab view "Auswahl" of window mainwindow to stop
	end if
end clicked


on will select tab view item theObject tab view item tabViewItem
	(*Add your script here.*)
end will select tab view item


on action theObject
	(*Add your script here.*)
end action

on will close theObject
	(*Add your script here.*)
end will close

on will open theObject
	(*Add your script here.*)
end will open

on should close theObject
	(*Add your script here.*)
end should close

on opened theObject
	(*Add your script here.*)
end opened

on will resize theObject proposed size proposedSize
	(*Add your script here.*)
end will resize

on will finish launching theObject
	
end will finish launching