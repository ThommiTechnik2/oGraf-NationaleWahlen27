import sqlite3, sys
Q = [
    ("Stand (abgeschl., Kantone, Gemeinden, Zeit)", "select wahl_abgeschlossen, kantone_abgeschlossen, gemeinden_abgeschlossen, timestamp from Stand"),
    ("Kantone abgeschlossen", "select group_concat(kanton_nummer) from Stand_Kantone where kanton_abgeschlossen=1"),
    ("Kantone in Stammdaten", "select count(*) from Kantone"),
    ("CH: Sitze, Summe Parteistärke", "select sum(anzahl_gewaehlte), round(sum(partei_staerke),3) from Ergebnis_Partei_CH"),
    ("Kantone: Sitze", "select sum(anzahl_gewaehlte) from Ergebnis_Partei_Kanton"),
    ("Kantone mit Parteistärke", "select count(distinct kanton_nummer) from Ergebnis_Partei_Kanton where partei_staerke is not null"),
    ("Kandidierende: gewählt, mit Stimmen, total", "select sum(flag_gewaehlt), count(stimmen_kandidat), count(*) from Kandidierende"),
    ("Listen: Sitze", "select sum(anzahl_gewaehlte) from Listen"),
    ("Gemeinden mit Parteistimmen", "select count(distinct gemeinde_nummer) from Ergebnis_Partei_Gemeinde where stimmen_partei is not null"),
    ("Beteiligung CH: Berechtigte, %", "select wahlberechtigte, round(wahlbeteiligung,2) from Wahlbeteiligung_CH"),
    ("Sondergemeinden (Ausland)", "select count(*) from Gemeinden where sondergemeinde=1"),
    ("Parteien ohne Stammdaten", "select group_concat(distinct e.partei_id) from Ergebnis_Partei_Kanton e left join Parteien p using(partei_id) where p.partei_id is null"),
    ("Kandidatenstimmen Kanton = Summe Gemeinden (Abweichungen)",
     """select count(*) from (select k.kanton_nummer,k.liste_nummer_bfs,k.kandidat_nummer,k.stimmen_kandidat s,
        (select sum(g.stimmen_kandidat) from Kandidierende_Gemeinde g where g.kanton_nummer=k.kanton_nummer
          and g.liste_nummer_bfs=k.liste_nummer_bfs and g.kandidat_nummer=k.kandidat_nummer) gs
        from Kandidierende k where k.stimmen_kandidat is not null) where gs is not null and gs<>s"""),
    ("Parteistimmen Kanton = Summe Gemeinden (Abweichungen)",
     """select count(*) from (select k.kanton_nummer,k.partei_id,k.stimmen_partei s,
        (select sum(g.stimmen_partei) from Ergebnis_Partei_Gemeinde g where g.kanton_nummer=k.kanton_nummer and g.partei_id=k.partei_id) gs
        from Ergebnis_Partei_Kanton k where k.stimmen_partei is not null) where gs is not null and gs<>s"""),
]
for path in sys.argv[1:]:
    db = sqlite3.connect(path)
    db.execute("create index if not exists ix_kg on Kandidierende_Gemeinde(kanton_nummer,liste_nummer_bfs,kandidat_nummer)")
    print("#####", path)
    for label, q in Q:
        try:
            print(f"  {label:58s} {db.execute(q).fetchall()}")
        except Exception as e:
            print(f"  {label:58s} FEHLER {e}")
