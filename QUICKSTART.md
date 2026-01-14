# 🚀 Hızlı Başlangıç - Web Arayüzü

## 1. Başlatın

```bash
source venv/bin/activate
python app.py
```

Tarayıcınızda açın: **http://localhost:5000**

## 2. Veri Yükleyin

"📊 Veri Yükle & Base Hesapla" butonuna tıklayın.

✅ İşlem tamamlandığında:
- Veri istatistikleri görünür
- Base cashflow Excel'i oluşturulur
- Senaryo oluşturma aktif olur

## 3. Senaryo Oluşturun

"➕ Yeni Senaryo Oluştur" butonuna tıklayın.

### Örnek 1: Ödeme Azaltma (Yıl Bazlı)

```
Senaryo Tipi: Kaza Yılı Bazlı
Senaryo Adı: test_2024
Kaza Yılları: 2024
Azaltma Oranı: 20
```

**Ne olur?** 2024 yılı Bodily dosyalarının 202409 ödemeleri %20 azalır.

### Örnek 2: Muallak Ödeme (Dosya Bazlı)

```
Tab: Muallak Ödeme
Senaryo Tipi: Dosya Bazlı
Senaryo Adı: muallak_test
Dosya Numaraları: 24448222
```

**Ne olur?** Bu dosyanın 202409 muallağı tamamen ödenir.

## 4. Karşılaştırın

En az 1 senaryo oluşturduktan sonra:

"📈 Karşılaştırma Oluştur" butonuna tıklayın.

✅ `comparison_all.xlsx` otomatik indirilir.

## 5. Dosyaları İndirin

Her senaryo kartında "⬇️ İndir" butonu var.

Ayrıca sol tarafta "⬇️ Base CF İndir" butonu.

## 🎯 Hızlı Test Senaryosu

### Senaryo 1: 2024 %20 Azaltma
- Tip: Ödeme Azaltma - Kaza Yılı
- Yıl: 2024
- Oran: %20

### Senaryo 2: Büyük Dosya Muallak
- Tip: Muallak Ödeme - Dosya Bazlı
- Dosya: 24448222

Comparison'da ikisini yan yana görürsünüz!

## 💡 İpuçları

**Hızlı Yıl Girişi:**
- Tek yıl: `2024`
- Çoklu: `2023,2024`
- Aralık: `2020-2024`

**Dosya No Girişi:**
- Virgülle ayırın: `24448222,500019,500036`
- Space'leri önemli değil

**Senaryo Yönetimi:**
- Oluşturduğunuz senaryolar session'da kalır
- Sayfayı yenilerseniz kaybolurlar
- Silmek için: 🗑️ butonu

**Karşılaştırma:**
- Otomatik tüm senaryoları dahil eder
- Base + her senaryo yan yana
- 4 sheet: Cumulative, CDF, Quarterly, Monthly

## 🐛 Sorun mu var?

**Veri yüklenmiyor:**
```bash
# Virtual environment aktif mi?
which python
# .../venv/bin/python olmalı

# CSV dosyası var mı?
ls -lh 202409_DATA.csv
```

**Port 5000 kullanımda:**
```bash
# Başka bir uygulama kullanıyor olabilir
lsof -i :5000

# app.py'de port'u değiştirin (örn: 5001)
app.run(debug=True, host='0.0.0.0', port=5001)
```

**Senaryo oluşturulamıyor:**
- Veriyi yüklediniz mi?
- Tüm alanları doldurdunuz mu?
- Console'da (F12) hata var mı?

## 📞 Yardım

Detaylı bilgi için: **README.md**

İyi analizler! 🎉
