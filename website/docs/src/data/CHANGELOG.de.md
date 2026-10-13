# Änderungen

Hier stehen alle wichtigen Änderungen. Das Projekt folgt [Semantic Versioning](https://semver.org/);
vor 1.0 können Minor-Versionen inkompatible Änderungen enthalten.

## [Unreleased]

## [0.5.6] – 2026-10-13

### Neu
- Impressum und Datenschutzerklärung auf rhinvoice.com, verlinkt von der Website, der Doku und der
  Anmeldeseite der öffentlichen Demo. Eigene Installationen zeigen sie nicht.

## [0.5.5] – 2026-10-13

### Neu
- Das Logo auf der Anmeldeseite führt zu rhinvoice.com, und die Leiste auf jeder Seite der
  öffentlichen Demo verlinkt die Website ebenfalls.

## [0.5.4] – 2026-10-13

### Neu
- Die Dokumentation unter [rhinvoice.com/docs](https://rhinvoice.com/docs/de/), auf Deutsch und
  Englisch: erste Schritte, die Regeln jedes Landes, Rechnungen, Umzug aus dem bisherigen Programm,
  Betrieb, häufige Fragen und diese Neuigkeiten. Funktionen, die nach der ersten öffentlichen
  Version dazugekommen sind, tragen den Hinweis «Ab Version …».
- Wie weitere Firmenländer dazukommen: ein Länderprofil pro Land, am Beispiel der Niederlande
  (Doku und Landingpage).

### Geändert
- Die Oberfläche verlinkt ihre Anleitungen (Backup, Installation, Importe) auf die Doku in ihrer
  Sprache statt auf Markdown-Dateien auf GitHub.

## [0.5.3] – 2026-10-13

### Behoben
- PDF-Fusszeile: Ein langer Handelsregistereintrag lief über den Seitenrand hinaus. Er steht jetzt
  mit einer Zeile pro kommagetrenntem Teil («Amtsgericht Kempten, HRB 12345»), und die Bezeichnung
  «Handelsregister» fällt weg, wenn der Eintrag sie schon nennt («Handelsregister des Kantons
  Zürich, …»).

## [0.5.2] – 2026-10-13

### Behoben
- Endet eine Sitzung, während die App offen ist (abgelaufen, anderswo abgemeldet oder durch das
  stündliche Zurücksetzen der Demo), führt das jetzt direkt zur Anmeldung, die den Grund nennt.
  Vorher zeigten Seiten «E-Mail-Adresse oder Passwort ist falsch.». Die API beantwortet solche
  Anfragen mit den Codes `session_expired` und `not_logged_in` statt `authentication_failed`; dieser
  Code gilt jetzt nur noch für falsche Anmeldedaten.

## [0.5.1] – 2026-10-13

### Geändert
- Die öffentliche Demo nimmt keine Dateien mehr an: Das Importieren von Kunden, Artikeln und
  Rechnungen ist dort abgeschaltet, und die Import-Seite erklärt, wie man es auf einer eigenen
  Installation ausprobiert. Anfragen an die Demo dürfen höchstens 2 MB gross sein.

## [0.5.0] – 2026-10-13

### Neu
- Alte Rechnungen lassen sich mit ihren Original-PDFs aus Ihrem bisherigen Programm übernehmen: eine
  Liste (CSV oder Excel) und der Ordner mit den PDF-Dateien, einzelne Dateien oder ZIP-Dateien. Jede
  wird zu einer gesperrten Rechnung mit Nummer, Datum, Kunde und Beträgen, ihr PDF gilt als die
  Rechnung; Mahnungen, Korrekturen und Kopien mit derselben Nummer bleiben als Anhänge erhalten.
  Kunden werden über Nummer oder Name gefunden, unbekannte werden angelegt und archiviert.
  Übernommene Rechnungen erscheinen in den Listen (markiert mit «Übernommen»), in der Suche, in der
  Dokumenthistorie des Kunden und im Umsatz, und offene können bezahlt werden. Der Nummernkreis für
  Rechnungen setzt hinter den übernommenen Nummern fort. Siehe docs/import.md und ADR 0019.
- Eine übernommene Rechnung ohne PDF erhält ihr PDF später auf ihrer Seite; weitere Dateien werden
  zu Anhängen.
- Deinstallieren: wie Container, Daten und Images entfernt werden (docs/install.md), und der Name
  der Installation in `.env` (`COMPOSE_PROJECT_NAME`).

## [0.4.3] – 2026-10-12

### Neu
- Kunden behalten das Datum, seit dem sie Kunden sind: Der Import liest es aus einer Spalte wie
  «Kunde seit», «Angelegt am» oder «Created» (14.03.2019, 2019-03-14, auch mit Uhrzeit), auch beim
  Aktualisieren bereits importierter Kunden. Die Kundenseite zeigt es neben der Nummer.
- Die Schweizer MWST-Sätze von 2011 bis 2017 (8 / 2.5 / 3.8 %): Artikellisten älterer Programme
  mit «8» als Satz lassen sich importieren, ebenso Dokumente mit einer Leistung in diesen Jahren.
- Artikeleinheiten wie «monatlich», «pro Monat», «jährlich» oder «wöchentlich».

## [0.4.2] – 2026-10-12

### Geändert
- Ein neues Logo: eine Rechnungsseite mit dem Rhein und seinen vier Ländern. Es ist das Favicon
  und das Symbol auf dem Startbildschirm von Smartphones und erscheint in der App, auf
  rhinvoice.com und in den Vorschaubildern.

## [0.4.1] – 2026-10-12

### Geändert
- Die öffentliche Demo nimmt Importe von höchstens 200 KB und 200 Zeilen an, damit sie sich nicht
  mit Datenmüll füllen lässt; die Import-Seite weist darauf hin. Eigene Installationen behalten
  ihre Grenzen (5 MB, 10'000 Zeilen).

## [0.4.0] – 2026-10-12

### Neu
- PDF-Ausgabe über Gotenberg mit einer Live-Papiervorschau im Editor; ausgestellte Dokumente
  behalten ihr erstes PDF (SHA-256).
- Swiss QR-Rechnung (QR-Referenz oder Creditor Reference) für die Schweiz und Liechtenstein,
  EPC-QR-Code (GiroCode) für Deutschland und Österreich sowie für Euro-Rechnungen aus der Schweiz
  und Liechtenstein an Kunden im EWR; die Pflichtangaben werden vor dem Ausstellen geprüft.
- Druckvorlagen (Klassisch, Modern, Schlicht) mit Position und Grösse des Logos, Schrift,
  Absenderzeile, Kontaktangaben, Positionsnummern und allen Bankkonten in der Fusszeile;
  ausgestellte Dokumente behalten das Layout vom Tag ihrer Ausstellung.
- Zahlungserinnerungen und Mahnungen in drei Stufen mit neuen Zahlungsfristen, optionalen Gebühren
  und Texten pro Sprache; das PDF fordert den offenen Betrag plus Gebühr.
- Import von Kunden und Artikeln aus CSV, XLSX und XLS mit Spaltenzuordnung, Testlauf, Umgang mit
  Duplikaten und gespeicherten Vorlagen.
- Backups mit restic in einem eigenen Container: täglich und nach dem Ausstellen, nach S3, SFTP,
  in einen lokalen Ordner oder über rclone nach Dropbox, Google Drive und weiteren Zielen; Stand in
  der Übersicht und in den Einstellungen, Wiederherstellen mit `make restore`.
- Einrichtungsassistent beim ersten Start (Land, Firma) und eine Checkliste zur Einrichtung in der
  Übersicht.
- Ein Hinweis im Editor, wenn einem Geschäftskunden in der EU die USt-IdNr. bzw. UID für das
  Reverse-Charge-Verfahren fehlt.
- E-Rechnungen: Jede ausgestellte Rechnung und Stornorechnung enthält in ihrem PDF eine ZUGFeRD- /
  Factur-X-Rechnung (EN 16931), für alle Länder und in der Druckvorlage abschaltbar; XRechnung 3.0
  zum Herunterladen für deutsche Behörden; die Rechnung zeigt an, was für das eine oder andere
  fehlt. In CI geprüft mit dem KoSIT-Validator und Mustang.

- Demodaten für eine Testinstallation: `rhinvoice demo` (oder `make demo`) legt Kunden, Artikel
  und Rechnungen, Zahlungen und Angebote aus rund 21 Monaten an.

- Die App startet nicht (und migriert nicht) auf einer Datenbank, die von einer neueren Version
  eingerichtet wurde, und sagt in einer Meldung, was zu tun ist, statt später bei einzelnen Aktionen
  zu scheitern.
- Wiederkehrende Rechnungen: Pläne, die jeden Monat, jedes Quartal, Halbjahr oder Jahr eine
  Rechnung schreiben, als Entwurf, ausgestellt oder ausgestellt und per E-Mail versendet, mit dem
  abgedeckten Zeitraum als Leistungszeitraum. Der Webserver schreibt sie selbst (jeden Zeitraum
  einmal, verpasste Zeiträume werden nachgeholt); `rhinvoice recurring` erledigt es sofort. Eine
  ausgestellte Rechnung lässt sich zu einer wiederkehrenden machen.
- Versand per E-Mail: Rechnungen, Angebote, Gutschriften und Mahnungen gehen mit ihrem PDF (und auf
  Wunsch der XRechnung) direkt aus Rhinvoice über den eigenen Mailserver der Firma (SMTP), der
  unter Einstellungen → E-Mail mit einer Testmail eingerichtet wird. Vorlagen pro Art und Sprache
  mit Platzhaltern (neu: `{firma}`); jede E-Mail wird im Verlauf des Dokuments vermerkt. Lehnt der
  Server eine E-Mail ab, wird seine Antwort angezeigt.
- Waren und Dienstleistungen: Artikel und Positionen geben an, was sie liefern. Waren an
  Unternehmen in der EU mit USt-IdNr. bzw. UID sind steuerfreie innergemeinschaftliche Lieferungen
  (E-Rechnungs-Kategorie K mit dem Lieferort), Waren, die das MWST- bzw. USt.-Gebiet verlassen,
  sind steuerfreie Ausfuhrlieferungen, auch an Privatkunden; jeweils mit eigenem Hinweis, auch auf
  gemischten Rechnungen. Der Editor erinnert an den Ausfuhr- bzw. Gelangensnachweis.

- Ein Sprachmenü oben rechts (auch auf der Anmeldeseite): Deutsch (Schweiz, Deutschland,
  Österreich) oder English, gespeichert pro Browser. Version, Lizenz und Links unter «Über
  Rhinvoice» im Kontomenü und unten in der Seitenleiste.

- Länderprofile: Alles, was sich zwischen der Schweiz, Liechtenstein, Deutschland und Österreich
  unterscheidet (Steuerrecht, Sätze, Hinweise, Pflichtangaben, Zahlungscodes, Begriffe), steht in
  einem Profil pro Land, das die Oberfläche über die API liest. Wie man ein Land hinzufügt,
  beschreibt `docs/adding-a-country.md`.

- Demomodus (`RHINVOICE_DEMO`) für eine öffentliche Demo: Die Daten werden jede Stunde
  zurückgesetzt, die Anmeldeseite meldet mit einem Klick an, was Besucher aussperren oder E-Mails
  versenden würde, wird abgelehnt, und Anmeldungen und Änderungen sind in ihrer Häufigkeit
  begrenzt. `deploy/demo/` betreibt die Schweiz, Deutschland und Österreich nebeneinander hinter
  Caddy, vom Internet abgeschottet.
- Höchstens zwei Passwortprüfungen (argon2, je 64 MiB) laufen gleichzeitig; viele Anmeldungen auf
  einmal warten, statt den Arbeitsspeicher zu erschöpfen.

### Behoben
- Die Übersicht behielt oben eine leere Lücke, nachdem die Checkliste ausgeblendet war.
- Der Import las einen Satz von 13 % als den österreichischen Satz von 10 %; die Sätze werden jetzt
  nach dem Land der Firma gelesen (13 % ist ein eigener Satz Österreichs, 16 % und 5 % sind deutsche
  Sätze von 2020). Ein Satz, den es im Land nie gab (z. B. 19 % für eine Schweizer Firma), wird
  gemeldet, statt als Normalsatz übernommen zu werden.
- Deutsche Dokumente drucken «Ihre USt-IdNr.» statt «Ihre UID»; die Steuer heisst überall «USt.».
- Der Einrichtungsassistent zeigt die aktuell gültigen Steuersätze statt eines festen Texts.
- Die Rappenrundung auf 5 Rappen und die QR-IBAN werden nur dort angeboten, wo sie gelten
  (Schweiz, Liechtenstein).
- Das Bezahlen oder Stornieren von Rechnungen, die eine frühere Version ausgestellt hatte, schlug
  mit einem Konflikt fehl.
- Stornorechnungen ohne Steuer schrieben ein Steuertotal von «-0.00» in ihre E-Rechnung, das
  Mustang ablehnt (BR-CO-14).
- Die Schaltfläche der Artikelliste hiess «Neuer Kunde».

### Geändert
- Rhinvoice steht unter der GNU Affero General Public License v3.0 oder später; Beiträge erfolgen
  unter einer Contributor License Agreement. Das Projekt liegt unter `github.com/rhinvoice/rhinvoice`
  und seine Images unter `ghcr.io/rhinvoice/rhinvoice`.
- Die Übersicht ist ein Cockpit: Umsatz dieses Jahres gegenüber dem Vorjahr mit Trendlinie, offene
  und überfällige Beträge, offene Angebote mit Annahmequote, offene Rechnungen nach Alter, die am
  längsten überfälligen, die besten Kunden, die erwarteten Zahlungen pro Woche und die letzten
  Aktivitäten, pro Währung.
- Die Architecture Decision Records sind auf Englisch geschrieben.
- Alle PDFs sind PDF/A-3b, erzeugt aus der Ausgabe von Chromium, ohne Seiten, Schriften oder Tags
  zu verändern.

## [0.3.0] – 2026-10-11

Erste Vorschauversion.

### Neu
- Angebote, Rechnungen und Stornorechnungen: erstellen, bearbeiten, ausstellen, als bezahlt
  markieren (auch teilweise), Zahlungen entfernen, stornieren, duplizieren, ein Angebot in eine
  Rechnung umwandeln.
- Berechnung mit Positions- und Gesamtrabatt, Netto- oder Bruttopreisen, Steuer pro Satz und
  Schweizer Rappenrundung auf 5 Rappen; datierte Steuersätze für die Schweiz, Liechtenstein,
  Deutschland und Österreich; automatische Steuerbehandlung (Inland, Reverse Charge, Export,
  Kleinunternehmer, steuerbefreit) mit protokolliertem manuellem Override.
- Nummern werden beim Ausstellen vergeben, ohne Lücken; ausgestellte Dokumente sind unveränderlich
  (auch durch die Datenbank erzwungen), Korrekturen nur per Storno.
- Rechnungs- und Angebotslisten mit Ansichten (offen, überfällig, bezahlt …) und Volltextsuche;
  Übersicht mit offenen, überfälligen und bezahlten Beträgen, Monatsumsatz und letzten Aktivitäten.
- Kunden und Artikel mit Suche, Archiv und Dokumenthistorie; Firma, Logo, Bankkonten
  (IBAN/QR-IBAN) und Nummernkreise in den Einstellungen.
- Anmeldung mit optionaler Zwei-Faktor-Authentifizierung, Tastenkürzel, Befehlspalette, Hell- und
  Dunkelmodus, Deutsch (CH/DE/AT) und Englisch.

### Noch nicht enthalten
- PDF-Ausgabe, Swiss QR-Rechnung und EPC-QR, E-Rechnungen, Import, Backup, Einrichtungsassistent.
