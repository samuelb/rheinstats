# Der Rhein bei Rekingen

Wie sich Wassertemperatur, Abfluss, Wasserstand und Wasserchemie des Rheins
über die Jahre verändert haben — bis zu 123 Jahrgänge Tagesmittel, jeder als
eigener Linienzug über den Jahresverlauf gelegt, eingefärbt von Blau (älteste)
nach Rot (jüngste Messung).

**→ [Zur Visualisierung](https://samuelb.github.io/rheinstats/)**

Eine Linie anklicken hebt ihr Jahr hervor; Hover und Pfeiltasten zeigen den Wert
am Zeigerdatum. Tabs schalten zwischen den Messgrössen um, zwei Schieberegler
auf der Farblegende grenzen den Jahresbereich ein.

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

| Parameter                        | Messbeginn beim BAFU |
| -------------------------------- | -------------------- |
| Abfluss (m³/s)                   | 1904                 |
| Wasserstand (m ü.M.)             | 1964                 |
| Wassertemperatur (°C)            | 1969                 |
| Elektrische Leitfähigkeit (µS/cm)| 1976                 |
| pH-Wert                          | 1976                 |
| Sauerstoff (mg/l und Sättigung %)| 1976                 |

### Primäre Quelle: Datenservice Hydrologie (`measurements/`)

Die vollständigen Messreihen liegen seit August 2026 als CSV-Export des
Datenservice Hydrologie des BAFU vor, im Ordner [`measurements/`](measurements/).
Wassertemperatur, Abfluss und Wasserstand sind lückenlos vom jeweiligen
Messbeginn bis zum Exportdatum (12. August 2026) abgedeckt — zusammen
123 Jahrgänge, 1904–2026. Die vier Wasserchemie-Reihen (ab 1976) tragen
quellenseitig einzelne Lücken; unvollständige Jahrgänge bleiben dort aus der
Trendberechnung ausgeschlossen.

### Ergänzende Quelle: hydrodaten.admin.ch

`fetch_hydrodaten.py` holt die Tagesmittel hinter den Jahresganglinien von
hydrodaten.admin.ch nach `rhein_rekingen_daily.csv`. Seit der Export vorliegt,
verwendet `build_site.py` diese Daten nur noch ergänzend — für Tage, die der
Export nicht abdeckt, also für die jüngsten Messwerte seit dem Exportdatum.
Im Überlappungsbereich stimmen beide Quellen überein (geprüft: maximale
Abweichung 0.02 am noch provisorischen letzten Tag).

Verbleibende Lücken der Darstellung:

- **29. Februar** wird nicht gezeigt; die Grafik nutzt ein 365-Tage-Raster.
- **2026** ist naturgemäss unvollständig.

Details zu allen geprüften Bezugsquellen in [`SOURCES.md`](SOURCES.md).

## Lizenz

Der Code steht zur freien Verfügung. Für die Messdaten gelten die oben genannten
Bedingungen des BAFU; bei einer Weiterverwendung ist das **Bundesamt für Umwelt
BAFU** als Quelle anzugeben.
