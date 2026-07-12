# Görev: MVP — uçtan uca çalışan ilk dikey dilim

## Amaç

Kullanıcının şematik tuvale bir Josephson jonksiyonu + kapasitör + okuma
rezonatörü koyup, bunları kablolayıp "Run" diyebildiği ve hem klasik hem kuantum
sonuçları dalga formu görüntüleyicide görebildiği, çalışan bir Windows uygulaması.

Dar ama GERÇEK olmalı. "Yarım özellik" değil, "az sayıda tam özellik".

## Bağımlılık sırası

GÖREV 1 BLOKLAYICIDIR. Netlist şeması bitmeden diğer görevler başlayamaz,
çünkü hepsi bu sözleşmeye göre kodlanacak.

### Görev 1 — Netlist şeması ve veri modeli  [BLOKLAYICI, önce bu]
Sahip: netlist-core

- Netlist JSON şemasını tanımla: elemanlar (id, tip, parametreler, birimler),
  düğümler (nodes), bağlantılar.
- MVP eleman tipleri: `junction` (Ic, Cj, Rn), `capacitor` (C), `inductor` (L),
  `resonator` (f0, Q), `transmission_line`, `current_source`, `ground`.
- Python veri modeli (dataclass) + JSON serialize/deserialize.
- Netlist doğrulama: kopuk düğüm, toprak yok, eksik parametre → anlamlı hata.
- Birim sistemi: her parametrenin birimi açıkça saklanır (GHz, fF, nA, ohm).
- ÖRNEK NETLIST DOSYALARI üret (`examples/`): en az bir transmon + rezonatör.
- Şemayı `docs/netlist_schema.md` dosyasında belgele.

Bu bitince lead'e haber ver; diğer teammate'ler bu şemaya göre çalışmaya başlar.

### Görev 2 — Klasik çözücü
Sahip: solver-classical

- RCSJ (resistively and capacitively shunted junction) modeli, zaman-domeni ODE.
- I-V eğrisi hesabı (akım süpürme).
- Faz dinamiği çıktısı.
- Okuma devresi: rezonatör + iletim hattı, S21 transmisyon eğrisi.
- Girdi: netlist. Çıktı: HDF5 sonuç dosyası.
- GUI'siz, komut satırından çalışabilir olmalı.

### Görev 3 — Kuantum çözücü
Sahip: solver-quantum

- Netlist + kapasitans matrisinden devre kuantizasyonu → Ej, Ec, g.
  (Kapasitans matrisi kullanıcı girdisi veya CSV — HESAPLAMA, sadece OKU.)
- scqubits/QuTiP kullanarak transmon spektrumu: enerji seviyeleri, E01,
  anharmonisite.
- Rezonatöre dispersif bağlanma → dispersif kayma (chi).
- Girdi: netlist. Çıktı: HDF5 sonuç dosyası.
- GUI'siz, komut satırından çalışabilir olmalı.

### Görev 4 — Şematik tuval (GUI)
Sahip: schematic-ui

- PySide6 QGraphicsView/QGraphicsScene tabanlı tuval.
- Sol panelde eleman kütüphanesi, sürükle-bırak.
- Elemanları kablolama (düğüm birleştirme), taşıma, silme.
- Sağ panelde seçili elemanın özellik/parametre editörü (birimli).
- Tuval → netlist JSON üretimi. Netlist JSON → tuval yükleme.
- Zoom, pan, grid snap.

### Görev 5 — Dalga formu görüntüleyici (GUI)
Sahip: waveform-ui

- pyqtgraph tabanlı çoklu kanal plot penceresi.
- HDF5 sonuç dosyasını okuyup çizer.
- İmleç (cursor), zoom, kanal aç/kapat, CSV/PNG export.
- Enerji seviyesi diyagramı ve S21 eğrisi için uygun görünümler.

### Görev 6 — Uygulama iskeleti ve entegrasyon
Sahip: app-core

- Ana pencere, menü, toolbar, "Run" akışı.
- Proje kaydet/yükle (.jjq = netlist JSON + metadata).
- Çözücü orkestrasyonu: hangi çözücü, hangi parametrelerle, ilerleme çubuğu.
- Uzun simülasyon sırasında GUI donmamalı (worker thread).
- PyInstaller ile Windows .exe build script'i.

### Görev 7 — Doğrulama  [sürekli, diğerlerine paralel]
Sahip: validation

- `tests/validation/` altında analitik limit testleri (CLAUDE.md'deki listeye bak).
- Birim tutarlılığı testleri.
- Referans bir transmon için bilinen literatür değerleriyle karşılaştırma.
- Diğer teammate'lerin sonuçlarını sorgula. Şüpheli bir sayı görürsen SÖYLE.

## Kabul kriterleri

- [ ] `pytest` tamamen geçiyor.
- [ ] `tests/validation/` altındaki analitik limit testleri geçiyor.
- [ ] Çözücüler GUI olmadan, komut satırından bir netlist dosyasıyla çalışıyor.
- [ ] Uygulama açılıyor; tuvale transmon + rezonatör kurulabiliyor.
- [ ] "Run" → sonuç → dalga formunda görüntüleniyor.
- [ ] Proje kaydedilip yeniden açılabiliyor.
- [ ] `core/` içinde hiçbir yerde PySide6 import edilmiyor.
- [ ] Windows'ta çalışan bir .exe üretilebiliyor.
- [ ] README'de kurulum ve ilk çalıştırma anlatılmış.

## Kapsam dışı (MVP'de YAPMAYIN)

- 3B EM / FEM alan çözücü, mesh üretici
- GDS layout editörü
- Pulse şekillendirme, gate fidelity optimizasyonu
- Çoklu qubit devreleri (MVP tek qubit + tek rezonatör)
- Purcell filtresi
- Ansys/palace entegrasyonu
- Bulut / lisanslama / kullanıcı hesabı
