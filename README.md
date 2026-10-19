![DxEinkaufsPlaner – Programmvorstellung](https://i.ibb.co/Z66YrPCX/Dx-Einkauf-Planer-Vorstellung.png)

# DxEinkaufsPlaner

**Einfach planen. Preise im Blick behalten. Clever einkaufen.**

DxEinkaufsPlaner ist eine Windows-Anwendung, mit der du deine Einkäufe, Produkte, Preise und Rezepte übersichtlich verwalten kannst. Das Programm vereint Einkaufsplanung, Rezeptverwaltung und einen zentralen Preiskatalog in einer modernen, dunklen Benutzeroberfläche mit orangefarbenen Akzenten.

Das Ziel: den Einkauf besser organisieren, Preise vergleichen und den Überblick über die eigenen Ausgaben behalten.

## Funktionen

### 🛒 Einkaufsplanung
- Einkaufslisten übersichtlich erstellen und verwalten
- Produkte schnell suchen und auswählen
- Einkäufe strukturiert vorbereiten

### 💶 Zentraler Preiskatalog
- Produkte mit Kategorien, Einheiten und Preisen verwalten
- Preise einzelnen Geschäften zuordnen
- Preise verschiedener Geschäfte vergleichen
- Produktdaten zentral in einer lokalen Datenbank speichern

### 🍲 Rezeptverwaltung
- Eigene Rezepte speichern und bearbeiten
- Zutaten aus dem vorhandenen Produktkatalog auswählen
- Mengen und Zutatenkosten verwalten
- Rezeptnotizen und Zubereitungshinweise hinterlegen
- Zutaten bequem über die Suchfunktion finden

### 🤖 KI-gestützte Kassenbon-Auswertung
DxEinkaufsPlaner unterstützt die Auswertung von Kassenbons mithilfe von Google Gemini.

Der Ablauf:
1. Ein Kassenbonfoto in Google Gemini hochladen.
2. Den bereitgestellten Prompt verwenden.
3. Die erkannte Produktliste in DxEinkaufsPlaner einfügen.
4. Produktnamen, Mengen und Preise prüfen.
5. Die bestätigten Produkte in den Preiskatalog übernehmen und einem Geschäft zuordnen.

Die Produktkategorien werden anhand der programminternen Zuordnungslogik vorgeschlagen und können im Prüfprozess kontrolliert werden.

### 💾 Lokale Datenspeicherung
- Produkte, Rezepte, Preise und Einkaufslisten werden lokal gespeichert.
- Die Datenbank liegt getrennt von den Programmdateien im Benutzerprofil.
- Dadurch können persönliche Daten bei Programmupdates grundsätzlich erhalten bleiben, sofern der Datenordner nicht gelöscht wird.

## Technologie

- Python
- Tkinter / CustomTkinter
- SQLite
- Selenium und Microsoft Edge für die Gemini-Integration
- Google Gemini zur Kassenbon-Auswertung
- PyInstaller und Inno Setup zur Erstellung eines Windows-Installers

## Voraussetzungen

- Windows
- Microsoft Edge für den beschriebenen Gemini-Workflow
- Internetverbindung und Google-Konto für die Nutzung von Google Gemini

Python muss bei Verwendung der fertig erstellten Installationsversion normalerweise nicht separat installiert werden.

## Installation

1. Die aktuelle Setup-Datei aus dem Bereich **Releases** herunterladen.
2. Den Installer ausführen.
3. DxEinkaufsPlaner starten.
4. Für die Kassenbon-Auswertung Google Gemini öffnen und dich mit deinem Google-Konto anmelden.

## Datenschutz

Die Anwendungsdaten werden lokal auf dem jeweiligen Computer gespeichert. Für die KI-gestützte Kassenbon-Auswertung werden Bonbilder und Anfragen an Google Gemini übermittelt. Dabei gelten die Datenschutzbedingungen und Nutzungsbedingungen von Google.

## Projektstatus

DxEinkaufsPlaner wird fortlaufend weiterentwickelt. Funktionen und Benutzeroberfläche können sich mit zukünftigen Versionen verändern.

## Feedback und Fehlerberichte

Feedback, Verbesserungsvorschläge und Fehlerberichte sind willkommen. Bitte beschreibe bei einem Fehler möglichst genau, wie er reproduziert werden kann.

---

**DxEinkaufsPlaner – Einkäufe organisieren, Rezepte planen und Preise im Blick behalten.**
