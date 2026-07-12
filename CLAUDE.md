# Proje Bağlamı — JJQubit Studio

## Ne yapıyoruz

Windows için, süperiletken qubit tasarımcılarına yönelik interaktif bir devre
simülatörü. Kullanıcı şematik tuvale Josephson jonksiyonu, kapasitör, rezonatör
gibi elemanlar sürükler, bunları kablolar, "Run" der; program hem klasik
(RCSJ, zaman-domeni) hem kuantum (Hamiltonyen, spektrum) analizi çalıştırır ve
sonuçları dalga formu görüntüleyicide gösterir.

Model: PSIM / SPICE (şematik → netlist → çözücü → dalga formu).
Model DEĞİL: COMSOL (3B alan çözücü). Bkz. "Yapmayacaklarımız".

## Tech stack

- Dil: Python 3.11+
- GUI: PySide6 (Qt) — QGraphicsView/QGraphicsScene şematik tuval için
- Grafik: pyqtgraph (canlı/interaktif), matplotlib (rapor/export)
- Sayısal: NumPy, SciPy (sparse eigensolver, ODE)
- Kuantum fizik: QuTiP, scqubits
- Proje dosyası: JSON (netlist + parametreler), HDF5 (simülasyon sonuçları)
- Test: pytest
- Paketleme: PyInstaller → tek .exe (Windows)
- Hız gereken döngüler: Numba. C++ (pybind11) SADECE profil ile darboğaz
  kanıtlandıysa.

## Mimari — netlist sözleşmesi

Projenin en önemli kuralı: GUI ile çözücü çekirdeği birbirinden AYRIDIR ve
sadece netlist üzerinden konuşurlar.

    Şematik tuval  →  netlist (JSON)  →  çözücü çekirdeği  →  sonuçlar (HDF5)  →  dalga formu
         [GUI]           [SÖZLEŞME]          [KERNEL]                              [GUI]

Sonuçları:
- Çekirdek (`core/`) GUI olmadan, sadece netlist dosyasıyla çalıştırılabilir
  ve test edilebilir olmalı. `core/` içinde PySide6 import etmek YASAK.
- GUI (`gui/`) fizik hesabı YAPMAZ. Sadece netlist üretir ve sonuç okur.

## Görev

Güncel görev tanımı `docs/task.md` dosyasındadır. Önce onu okuyun.

## Yapmayacaklarımız (bunlar hata değil, karar)

Bu maddeleri "eksik" görüp tamamlamaya çalışmayın. Bunlar bilinçli kapsam dışıdır:

1. **3B Maxwell / FEM alan çözücü YAZMAYIN.** Kapasitans matrisi bu programın
   GİRDİSİDİR, çıktısı değil. Kullanıcı elle girer veya CSV'den yükler.
   (Ansys/palace entegrasyonu v2 konusudur.)
2. **Fizik kütüphanelerini sıfırdan yazmayın.** QuTiP ve scqubits doğrulanmış
   araçlardır. Transmon Hamiltonyeni, Lindblad çözücü vb. için bunları KULLANIN,
   yeniden implemente etmeyin. Kendi kodumuz bunların üstünde ince bir katman olmalı.
3. **Mesh üretici, GDS editörü, pulse optimizasyonu** — hepsi v2. MVP'de yok.

## Fizik doğrulama kuralı (ÖNEMLİ)

Bu bir fizik programı. Testin geçmesi sonucun DOĞRU olduğu anlamına gelmez.
Her sayısal çözücü için, bilinen analitik limitlere karşı doğrulama testi
yazılmalıdır. Örnekler:

- Transmon limitinde (Ej/Ec >> 1) anharmonisite ≈ -Ec çıkmalı.
- Ej/Ec → 0 limitinde sistem Cooper pair box davranışına yaklaşmalı.
- RCSJ çözücüsü, I < Ic için sıfır DC gerilim vermeli.
- Dispersif kayma χ, bilinen analitik ifadeye yakınsamalı.

Bu doğrulamalar `tests/validation/` altında yaşar ve bir sonucu "doğru" ilan
etmeden önce çalıştırılmalıdır. Sayısal sonuçların birimleri her zaman açıkça
belirtilmelidir (GHz, fF, nA, ...). Birim karışıklığı bu alandaki en yaygın
hata kaynağıdır.

## Dosya sahipliği (çakışmayı önlemek için)

Her teammate SADECE kendi klasöründe yazar. Başkasının klasöründeki bir dosyanın
değişmesi gerekiyorsa, o dosyanın sahibine mesaj atın — kendiniz düzenlemeyin.

    core/netlist/     → netlist şeması, veri modeli, doğrulama
    core/solvers/classical/  → RCSJ, ODE, I-V, S-parametreleri
    core/solvers/quantum/    → kuantizasyon, Hamiltonyen, spektrum
    gui/schematic/    → şematik tuval, eleman kütüphanesi, kablolama
    gui/waveform/     → dalga formu görüntüleyici
    gui/app.py        → ana pencere (sadece gui sahibi dokunur)
    tests/            → herkes kendi modülünün testini yazar
    tests/validation/ → validation teammate sahibi

## Çalışma kuralları

- Kod, değişken adları, yorumlar ve commit mesajları İNGİLİZCE. Dokümanlar Türkçe.
- İş bitince `pytest` çalıştırın. Testler geçmeden "tamamlandı" demeyin.
- Kararsız kaldığınızda tahmin etmeyin, lead'e sorun. Fizik konusunda tahmin
  yürütmek özellikle tehlikelidir.
- Bir kütüphanenin API'sinden emin değilseniz, uydurmayın — dokümanı kontrol edin.
- Public fonksiyonlara type hint ve docstring yazın. Docstring'de birimleri belirtin.

## Sınırlar

- `main` branch'e push YOK. Çalışmayı `claude/<özellik>` branch'inde yapın.
- Yıkıcı komutlar yasak: `rm -rf`, force push, `git reset --hard`.
- Yeni bir üçüncü parti bağımlılık eklemeden önce lead'e sorun.
- Riskli veya kapsam dışı bir şey gerekiyorsa UYGULAMAYIN — önerin, ben karar veririm.
