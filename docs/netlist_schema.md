# Netlist Şeması ve Veri Modeli (Task #1 — SÖZLEŞME)

Bu belge, JJQubit Studio'nun **netlist sözleşmesini** tanımlar. Şematik tuval
(GUI) netlist üretir; klasik ve kuantum çözücüler netlist tüketir. Her iki taraf
da burada tanımlanan alan adlarına ve Python API'sine göre kodlanır.

Modül: `core/netlist/` — saf veri (yalnızca stdlib). `core/` içinde **PySide6 /
GUI import edilmez**.

> Kural: Kod, alan adları ve tanımlayıcılar İNGİLİZCE'dir. Bu belgenin açıklama
> metni Türkçedir; alan adları (`nodes`, `params`, `Ic` ...) İngilizce kalır.

---

## 1. Genel yapı

Bir netlist üç üst düzey koleksiyondan oluşur:

- **`nodes`** — devrenin elektriksel düğümleri (string id listesi).
- **`elements`** — devre elemanları (`id`, `type`, birimli `params`).
- **`connections`** — kablolama: her bağlantı, bir elemanın bir **ucunu**
  (0-tabanlı terminal indeksi) tam olarak bir düğüme bağlar.

Topoloji modeli SPICE'a sadıktır ve **tek doğruluk kaynağıdır**: aynı düğüme
bağlı iki terminal elektriksel olarak aynı noktadır; elemanlar birbirine böyle
kablolanır. Ayrı bir "wire" nesnesi yoktur — kablolama tamamen `connections`
listesindedir.

### JSON üst düzey alanları

| Alan          | Tip            | Açıklama                                            |
|---------------|----------------|----------------------------------------------------|
| `format`      | string         | Her zaman `"jjqubit-netlist"`.                     |
| `version`     | string         | Şema sürümü. Güncel: `"1.0"`.                      |
| `name`        | string         | İnsan tarafından okunabilir devre adı.            |
| `nodes`       | string[]       | Bildirilen düğüm id'leri.                          |
| `elements`    | Element[]      | Devre elemanları (aşağıya bakın).                 |
| `connections` | Connection[]   | Terminal → düğüm bağlamaları.                      |

### Element nesnesi

```json
{ "id": "J1", "type": "junction", "params": { "Ic": {"value": 30.0, "unit": "nA"} } }
```

| Alan     | Tip                         | Açıklama                                     |
|----------|-----------------------------|----------------------------------------------|
| `id`     | string                      | Netlist içinde benzersiz eleman id'si.       |
| `type`   | string                      | Eleman tipi (bkz. Bölüm 3).                  |
| `params` | { name: Quantity }          | Parametre adı → birimli değer.               |

### Connection nesnesi

```json
{ "element": "J1", "terminal": 0, "node": "q" }
```

| Alan       | Tip     | Açıklama                                                    |
|------------|---------|------------------------------------------------------------|
| `element`  | string  | Bağlanan elemanın `id`'si.                                 |
| `terminal` | int     | Eleman tipinin terminal listesine 0-tabanlı indeks.        |
| `node`     | string  | Bu terminalin bağlandığı düğüm id'si.                       |

---

## 2. Birimler (Quantity)

Her sayısal parametre **açık bir birim taşır**. Birim karışıklığı bu alandaki en
yaygın hata kaynağıdır; bu yüzden birimler birinci sınıftır. Bir `Quantity`
şöyle serialize edilir:

```json
{ "value": 7.2, "unit": "GHz" }
```

- `value` sayıdır (int verilirse `float`'a çevrilir).
- `unit` kayıtlı bir birim jetonudur. Bilinmeyen birim `UnitError` fırlatır.
- Birimler ASCII'dir. **Mikro öneki `u`** ile yazılır (`uA`, `um`, `us`).
- Boyutsuz büyüklükler (kalite faktörü `Q`, etkin geçirgenlik `eps_eff`) **boş
  birim** `""` kullanır. Girişte `"1"` ve `"dimensionless"` de kabul edilir.

`Quantity.to_si()` değeri, boyutunun SI temel birimine çevirir (ör.
`Quantity(2, "fF").to_si()` → `2e-15` F). Çözücüler bu yardımcı ile birim
dönüşümünü elle yapmaktan kurtulur.

### Kayıtlı birimler (boyuta göre)

| Boyut           | SI temel | Kabul edilen jetonlar                          |
|-----------------|----------|------------------------------------------------|
| `frequency`     | `Hz`     | `Hz`, `kHz`, `MHz`, `GHz`, `THz`               |
| `capacitance`   | `F`      | `F`, `mF`, `uF`, `nF`, `pF`, `fF`, `aF`        |
| `inductance`    | `H`      | `H`, `mH`, `uH`, `nH`, `pH`                     |
| `current`       | `A`      | `A`, `mA`, `uA`, `nA`, `pA`                     |
| `resistance`    | `ohm`    | `ohm`, `kohm`, `Mohm`                          |
| `length`        | `m`      | `m`, `cm`, `mm`, `um`, `nm`                     |
| `time`          | `s`      | `s`, `ms`, `us`, `ns`, `ps`                     |
| `voltage`       | `V`      | `V`, `mV`, `uV`                                |
| `dimensionless` | (yok)    | `""`, `1`, `dimensionless`                      |

Bir parametrenin birimi, o parametre için beklenen **boyutta** olmalıdır. Örneğin
`Ic` bir `current`'tır; `Ic`'ye `GHz` (frequency) vermek bir doğrulama hatasıdır.

---

## 3. Eleman tipleri (MVP)

Her eleman tipinin **sabit sayıda ve sabit adlı terminalleri** vardır.
`connections` içindeki `terminal`, aşağıdaki terminal listesine 0-tabanlı
indekstir. Tablodaki birim sütunu **önerilen/tipik** birimdir; şema aynı boyuttaki
her birimi kabul eder.

### `junction` — Josephson jonksiyonu
- Terminaller: `[p, n]` (0 = p, 1 = n)
- Parametreler:
  - `Ic` — kritik akım (`current`, tipik `nA`)
  - `Cj` — jonksiyon öz-kapasitansı (`capacitance`, tipik `fF`)
  - `Rn` — normal-durum direnci (`resistance`, tipik `kohm`)

### `capacitor` — kapasitör
- Terminaller: `[a, b]`
- Parametreler: `C` — kapasitans (`capacitance`, tipik `fF`)

### `inductor` — indüktör
- Terminaller: `[a, b]`
- Parametreler: `L` — indüktans (`inductance`, tipik `nH`)

### `resistor` — direnç
- Terminaller: `[a, b]`
- Parametreler: `R` — direnç (`resistance`, tipik `ohm`)
- Kullanım alanı: eşleşmiş yük / port sonlandırması (ör. bir besleme hattının
  50 ohm ile sonlandırılması) ve kayıplı elemanlar. MVP eleman listesine bu
  ihtiyaç nedeniyle sonradan eklendi (bkz. `docs/task.md` — lead onayı ile).

### `resonator` — topraklı LC rezonatör (yığılı/lumped)
- Terminaller: `[a, b]`
- Parametreler:
  - `f0` — rezonans frekansı (`frequency`, tipik `GHz`)
  - `Q` — kalite faktörü (`dimensionless`, birim `""`)

### `transmission_line` — iletim hattı (2 uçlu besleme hattı)
- Terminaller: `[in, out]` (ortak dönüş toprak kabul edilir)
- Parametreler:
  - `Z0` — karakteristik empedans (`resistance`/ohm, tipik `ohm`)
  - `length` — fiziksel uzunluk (`length`, tipik `mm`)
  - `eps_eff` — etkin bağıl geçirgenlik (`dimensionless`); faz hızı
    `v = c / sqrt(eps_eff)`, gecikme `length / v`.

### `current_source` — akım kaynağı
- Terminaller: `[pos, neg]`
- Parametreler: `I` — beslenen akım (`current`, tipik `nA`)
- İşaret anlaşması: pozitif `I`, `pos` terminalinden devreye doğru akar.

### `ground` — toprak (0 V referansı)
- Terminaller: `[gnd]` (tek terminal)
- Parametreler: yok. `ground` elemanının bağlandığı düğüm, devrenin 0 V
  referansıdır.

---

## 4. Doğrulama (validation)

`validate(netlist)` netlist'i denetler ve sorun bulursa `ValidationError`
fırlatır. `ValidationError.errors`, her sorun için bir mesaj içerir ve suçlu
eleman/düğüm/parametreyi adıyla belirtir. Tüm sorunlar tek seferde toplanır
(ilkinde durulmaz). Sadece liste isteniyorsa `collect_errors(netlist)` kullanın.

Denetlenen hata modları:

1. Yinelenen eleman id'si.
2. Yinelenen düğüm id'si.
3. Bilinmeyen eleman tipi.
4. Eksik zorunlu parametre.
5. Beklenmeyen (tanımsız) parametre.
6. Parametre biriminin yanlış boyutta olması (ör. `Ic` = `GHz`).
7. Var olmayan bir elemana referans veren bağlantı.
8. Bildirilmemiş bir düğüme referans veren bağlantı.
9. Eleman tipi için aralık dışı terminal indeksi.
10. Bağlanmamış veya birden fazla kez bağlanmış terminal.
11. Hiç `ground` elemanı yok (0 V referansı yok).
12. Kopuk (floating) düğüm: ikiden az terminal bağlı.
13. Toprağa elektriksel olarak bağlı olmayan düğüm.

> Not: Kopuk düğüm kuralı (madde 12) SPICE alışkanlığına uyar: her düğümün en az
> iki terminali olmalıdır. Bu nedenle örnek devrelerdeki besleme hattı çıkışı bir
> `resistor` (eşleşmiş 50 ohm yük) ile sonlandırılır — bir port kapasitörü DEĞİL,
> çünkü S21 hesabı gerçek bir sonlandırma direnci gerektirir.

---

## 5. Python API

Import kökü: `core.netlist`.

```python
from core.netlist import (
    Netlist, Element, Connection, Quantity,      # veri modeli
    ElementType, ParamSpec, ELEMENT_TYPES,       # tip kaydı (registry)
    load, loads, dump, dumps, to_dict, from_dict,# JSON I/O
    validate, collect_errors,                    # doğrulama
    known_units, unit_dimension, is_known_unit,  # birim yardımcıları
    NetlistError, SchemaError, UnitError, ValidationError,  # istisnalar
)
```

Tipik kullanım:

```python
nl = load("examples/transmon_readout.json", validate=True)
for el in nl.elements:
    print(el.id, el.type, {k: (q.value, q.unit) for k, q in el.params.items()})

# Bir elemanın uçlarının bağlı olduğu düğümler (terminal sırasına göre):
nl.nodes_of("J1")          # -> ["q", "gnd"]
nl.terminals_on_node("q")  # -> o düğüme bağlı Connection listesi
```

İstisna hiyerarşisi: hepsi `NetlistError`'dan türer.
- `SchemaError` — bozuk JSON/dict yapısı (deserialize sırasında).
- `UnitError` — bilinmeyen birim jetonu.
- `ValidationError` — anlamsal doğrulama hatası; `.errors` listesini taşır.

`from_dict(to_dict(nl)) == nl` ve `loads(dumps(nl)) == nl` **kayıpsız**dır.

---

## 6. Örnek netlistler

`examples/` altında, kendi doğrulamasından geçen örnekler:

- **`examples/transmon_readout.json`** — bir transmon (junction + shunt
  kapasitör), okuma rezonatörüne kuplaj kapasitörüyle bağlı; rezonatör bir
  iletim hattı (besleme hattı) üzerinden okunur ve hat 50 ohm'luk bir
  `resistor` ile (eşleşmiş yük olarak) sonlandırılır. Düğümler: `gnd, q, r,
  fin, fout`.
- **`examples/rcsj_bias.json`** — akımla sürülen bir RCSJ jonksiyonu
  (current_source + junction + shunt kapasitör + indüktör). Klasik I-V için.

İki örnek birlikte sekiz MVP eleman tipinin (junction, capacitor, inductor,
resistor, resonator, transmission_line, current_source, ground) tamamını
kapsar.
