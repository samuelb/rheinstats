# Der Rhein bei Rekingen

Wie sich Wassertemperatur, Abfluss und Wasserstand des Rheins über die Jahre
verändert haben — 42 Jahrgänge Tagesmittel, jeder als eigener Linienzug über den
Jahresverlauf gelegt, eingefärbt von Blau (älteste) nach Rot (jüngste Messung).

**→ [Zur Visualisierung](https://samuelb.github.io/rheinstats/)**

Eine Linie anklicken hebt ihr Jahr hervor; Hover und Pfeiltasten zeigen den Wert
am Zeigerdatum. Tabs schalten zwischen Temperatur, Abfluss und Wasserstand um.

## Datenquelle

Sämtliche Messwerte stammen vom

> **Bundesamt für Umwelt BAFU, Abteilung Hydrologie**
> Messstation **2143 Rhein – Rekingen**
> <https://www.hydrodaten.admin.ch/de/seen-und-fluesse/stationen-und-daten/2143>

Das BAFU betreibt die Station, erhebt und prüft die Werte. Dieses Repository
enthält weder eigene Messungen noch eigene Berechnungen der Messreihen — es holt
die vom BAFU publizierten Tagesmittel ab und stellt sie dar.

Die Daten unterliegen den [Liefer- und Nutzungsbedingungen für hydrologische
Daten des BAFU](https://www.bafu.admin.ch/dam/de/sd-web/g7vjiKP5LJ11/liefer-nutzungsbedingungen-hydrologische-daten.pdf)
(Stand 13.7.2020). Darin heisst es:

> Die gelieferten Daten stehen zur freien Nutzung zur Verfügung. Der Kunde darf
> die Daten zu kommerziellen und nicht kommerziellen Zwecken verwenden. Die
> Angabe der Quelle wird empfohlen.

Das BAFU übernimmt keine Gewähr für Richtigkeit, Genauigkeit, Aktualität,
Zuverlässigkeit und Vollständigkeit der Daten. Fehler in dieser Darstellung sind
nicht dem BAFU anzulasten.

## Messreihe der Station 2143

| Parameter                 | Messbeginn beim BAFU |
| ------------------------- | -------------------- |
| Abfluss (m³/s)            | 1904                 |
| Wasserstand (m ü.M.)      | 1964                 |
| Wassertemperatur (°C)     | 1969                 |

Öffentlich als Tagesmittel abrufbar ist allerdings nur **1981 bis heute**. Damit
deckt diese Visualisierung 42 Jahrgänge ab. Bekannte Lücken, alle quellenbedingt:

- **1983, 1985, 1986** liefert das Portal für keinen Parameter Tagesdaten.
- **1988** liefert nur den 1. Januar — zu wenig für einen Linienzug, deshalb hier
  ausgelassen.
- **29. Februar** fehlt durchgehend; die Quelle nutzt ein 365-Tage-Raster.
- **2026** ist naturgemäss unvollständig.

Die Lücken sind nicht auf einen Stationsausfall zurückzuführen: dieselben Jahre
fehlen auch bei anderen Stationen (2289 Basel, 2091 Rheinfelden), deren Reihen
weit länger sind.

Als **Monatsmittel** reichen die öffentlichen Daten deutlich weiter zurück — beim
Abfluss bis 1904, bei der Temperatur bis 1970, beim Wasserstand bis 1974, und
zwar lückenlos. Die **vollständigen Tagesreihen ab 1904/1964/1969** gibt es
kostenlos beim [Datenservice Hydrologie](https://www.bafu.admin.ch/de/datenservice-hydrologie-fuer-fliessgewaesser-und-seen)
des BAFU (hydrologie@bafu.admin.ch).

Details zu allen geprüften Bezugsquellen in [`SOURCES.md`](SOURCES.md).

## Lizenz

Der Code steht zur freien Verfügung. Für die Messdaten gelten die oben genannten
Bedingungen des BAFU; bei einer Weiterverwendung ist das **Bundesamt für Umwelt
BAFU** als Quelle anzugeben.
