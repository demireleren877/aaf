# Cashflow Pattern Senaryo Analizi

202409 YEARMONTH ödemelerinin cashflow pattern'e etkisini analiz eder.

## 🚀 İki Kullanım Yöntemi

### 1. Web Arayüzü (Önerilen)

Modern, kullanıcı dostu web arayüzü:

```bash
# Virtual environment aktif et
source venv/bin/activate

# Web arayüzünü başlat
python app.py

# Tarayıcıda aç: http://localhost:5000
```

**Özellikler:**
- 📊 Görsel veri özeti ve istatistikler
- ➕ Kolay senaryo oluşturma (4 farklı tip)
- 📈 Otomatik karşılaştırma
- ⬇️ Tek tıkla dosya indirme
- 🗑️ Senaryo yönetimi

### 2. Komut Satırı (CLI)

Klasik terminal arayüzü:

```bash
# Virtual environment aktif et
source venv/bin/activate

# Ana programı çalıştır
python main.py
```

## 📋 Senaryo Tipleri

### 1. Ödeme Azaltma - Kaza Yılı Bazlı
- Belirli yılların 202409 ödemelerini % azaltır
- Sadece MB_FINAL='Bodily' dosyalara uygulanır
- Örnek: 2023-2024 yılları %20 azaltma

### 2. Ödeme Azaltma - Dosya Bazlı
- Belirli dosyaların 202409 ödemelerini sıfırlar
- Direkt CLAIM_NO ile seçim
- Örnek: 24448222, 500019 dosyaları ödenmez

### 3. Muallak Ödeme - Kaza Yılı Bazlı
- Belirli yılların 202409 muallağının %'sini öder
- Sadece MB_FINAL='Bodily' dosyalara uygulanır
- OS_TL → PAID_TL transfer
- Örnek: 2023-2024 muallağın %10'u ödenir

### 4. Muallak Ödeme - Dosya Bazlı
- Belirli dosyaların 202409 muallağını tamamen öder
- Direkt CLAIM_NO ile seçim
- OS_TL tamamen PAID_TL'ye eklenir
- Örnek: 24448222 dosyasının muallağı tamamen ödenir

## 📊 Çıktılar

`output/` klasöründe:

1. **base_cashflow.xlsx** - Base cashflow pattern (6 sheet)
2. **scenario_{name}.xlsx** - Her senaryo için (6 sheet)
3. **comparison_all.xlsx** - Karşılaştırma (4 sheet)

### Excel İçeriği

**Senaryo Dosyaları** (base_cashflow.xlsx, scenario_*.xlsx):
- data
- kümül data
- üçgen
- dev factorleri (CDF, ağırlıklar)
- cashflow pattern (60 period, kaza yılı bazlı)
- 180 aylık pattern (kaza yılı bazlı)

**Karşılaştırma Dosyası** (comparison_all.xlsx):
- Cumulative Payments - Kümül ödemeler yan yana
- CDF Comparison - CDF değerleri yan yana
- Quarterly CF Pattern - Çeyreklik normalize ağırlık (kaza yılı bazlı)
- Monthly CF Pattern - Aylık normalize ağırlık (kaza yılı bazlı)

## 🎯 Örnek Kullanım

### Web Arayüzü

1. "Veri Yükle & Base Hesapla" butonuna tıklayın
2. "Yeni Senaryo Oluştur" ile senaryo ekleyin
3. "Karşılaştırma Oluştur" ile comparison Excel'i oluşturun
4. İstediğiniz dosyayı indirin

### Komut Satırı

#### Kaza Yılı Bazlı Ödeme Azaltma
```
$ python main.py

Senaryo tipi? 1

Senaryo adı: test_2023_2024
Kaza yılları: 2023,2024
Azaltma oranı (%): 20

→ 2023-2024 yılları için %20 azaltma (sadece Bodily)
```

#### Dosya Bazlı Muallak Ödeme
```
$ python main.py

Senaryo tipi? 4

Senaryo adı: muallak_test
CLAIM_NO'lar: 24448222,500019

→ Bu dosyaların muallağı tamamen ödenir
```

## 📁 Ana Veri Dosyaları

- **202409_DATA.csv** - Ana veri (70MB, 846K satır)
  - CLAIM_NO, YEARMONTH, ORIGIN_YEAR
  - PAID_TL, OS_TL, MB_FINAL
- **data.xlsx** - Örnek veri formatı

## 🔧 Teknik Detaylar

- **Period**: Çeyrek yıl bazlı (quarterly)
- **CDF**: Cumulative Development Factor
- **Pattern**: Normalize ağırlık (her yıl için ayrı)
- **MB_FINAL**: Bodily filtreleme (kaza yılı bazlı senaryolarda)
- **202409**: Hedef dönem (tüm senaryolar bu döneme uygulanır)

## 📂 Dosya Yapısı

```
project/
├── app.py                 # Flask web uygulaması ⭐ YENİ
├── main.py                # CLI ana program
├── triangle_processor.py  # CF pattern hesaplama
├── utils.py              # Excel export
├── templates/
│   └── index.html        # Web arayüzü
├── 202409_DATA.csv       # Ana veri
├── data.xlsx             # Örnek veri
└── output/               # Çıktı klasörü
    ├── base_cashflow.xlsx
    ├── scenario_*.xlsx
    └── comparison_all.xlsx
```

## 💡 İpuçları

**En Etkili Yıllar:**
- 2024: 96.5M TL (%83)
- 2023: 18.7M TL (%16)

**Yıl Formatları:**
- Tek: `2024`
- Çoklu: `2023,2024`
- Aralık: `2020-2024`

**Senaryo Kombinasyonları:**
- Farklı tipleri karıştırabilirsiniz
- Her senaryo bağımsız çalışır
- Hepsi tek bir comparison Excel'de

**Web Arayüzü Avantajları:**
- Görsel feedback
- Kolay senaryo yönetimi
- Dosya indirme kolaylığı
- Session bazlı çalışma

## ❓ Sık Sorulan Sorular

**S: Web arayüzü mü CLI mı kullanmalıyım?**
- Web arayüzü: Daha kolay, görsel, önerilen
- CLI: Otomasyon, script'ler için

**S: Hangi senaryoyu kullanmalıyım?**
- Ödeme Azaltma: "Ödenmeseydi ne olurdu?"
- Muallak Ödeme: "Muallak ödenseydi ne olurdu?"
- Yıl bazlı: Genel trend analizi (Bodily only)
- Dosya bazlı: Spesifik dosya etkisi

**S: MB_FINAL='Bodily' filtresi neden?**
- Kaza yılı bazlı senaryolarda mantıklı segmentasyon
- Dosya bazlı senaryolarda kullanıcı direkt seçim yapıyor

**S: Muallak ödeme senaryosunda OS_TL ne oluyor?**
- Yıl bazlı: OS_TL azalır (kalan muallak gösterilir)
- Dosya bazlı: OS_TL sıfırlanır (tamamen ödendi)

**S: Base değişiyor mu?**
- Hayır, base her zaman aynı (orijinal data)

**S: Kaç senaryo oluşturabilirim?**
- Web: Session süresince sınırsız
- CLI: İstediğiniz kadar
- Hepsi comparison'da yan yana

## 🛠️ Kurulum

```bash
# 1. Virtual environment oluştur (ilk seferinde)
python3 -m venv venv

# 2. Aktif et
source venv/bin/activate

# 3. Gerekli paketleri yükle
pip install pandas numpy openpyxl flask

# 4. Hazırsınız!
python app.py  # Web arayüzü
# veya
python main.py  # CLI
```

## 🐛 Sorun Giderme

**Web arayüzü açılmıyor:**
```bash
# Flask kurulu mu?
pip list | grep -i flask

# Port 5000 kullanımda mı?
lsof -i :5000
```

**"Session expired" hatası:**
- Tarayıcı session'ını temizleyin
- Sayfayı yenileyin (F5)

**Veri yüklenemiyor:**
- Virtual environment aktif mi?
- 202409_DATA.csv dosyası var mı?
- Yeterli disk alanı var mı? (min 200MB)

## 🎉 Yeni Özellikler

✨ **Web Arayüzü** (v2.0)
- Modern, gradient renkler
- Real-time istatistikler
- Drag & drop hazır (gelecek sürüm)
- Session yönetimi

🔧 **4 Senaryo Tipi**
- Ödeme Azaltma (Yıl/Dosya)
- Muallak Ödeme (Yıl/Dosya)
- Bodily filtreleme
- OS_TL yönetimi

📊 **Gelişmiş Karşılaştırma**
- Normalize ağırlık bazlı
- Kaza yılı detayı
- Her yıl için ayrı pattern

İyi analizler! 🚀
