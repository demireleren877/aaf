"""
Cashflow Pattern Senaryo Analizi - Ana Script

Çıktılar (output/ klasörü):
1. base_cashflow.xlsx - Base cashflow pattern
2. scenario_{name}.xlsx - Her senaryo için
3. comparison_all.xlsx - Tüm senaryoların karşılaştırması
"""

import pandas as pd
import os
from triangle_processor import process_data_to_triangle
from utils import export_triangle_to_excel


def load_and_prepare_data(csv_file='202409_DATA.csv'):
    """Ana veriyi yükler ve hazırlar."""
    print(f"\n{csv_file} dosyası yükleniyor...")
    df = pd.read_csv(csv_file, delimiter=';')

    print(f"  ✓ {len(df):,} satır yüklendi")

    # Tarih dönüşümü
    df['DEVELOPMENT_DATE_PARSED'] = pd.to_datetime(df['DEVELOPMENT_DATE'], format='%d.%m.%Y', errors='coerce')

    # PAID_TL'yi numeric'e çevir (boş değerleri 0 yap)
    if df['PAID_TL'].dtype == 'object':
        df['PAID_TL'] = df['PAID_TL'].astype(str).str.replace(',', '.').replace('', '0').replace('nan', '0')
        df['PAID_TL'] = pd.to_numeric(df['PAID_TL'], errors='coerce').fillna(0)

    # OS_TL'yi numeric'e çevir (boş değerleri 0 yap)
    if df['OS_TL'].dtype == 'object':
        df['OS_TL'] = df['OS_TL'].astype(str).str.replace(',', '.').replace('', '0').replace('nan', '0')
        df['OS_TL'] = pd.to_numeric(df['OS_TL'], errors='coerce').fillna(0)

    df['ORIGIN_YEAR'] = df['ORIGIN_YEAR'].astype(int)
    df['CLAIM_NO'] = df['CLAIM_NO'].astype(str)

    return df


def convert_to_cashflow_format(df):
    """CSV datasını cashflow analiz formatına dönüştürür."""
    # Kaza yılı ve development date'e göre grupla
    df_grouped = df.groupby(['ORIGIN_YEAR', 'DEVELOPMENT_DATE_PARSED'])['PAID_TL'].sum().reset_index()

    # Cashflow format
    df_output = pd.DataFrame({
        'ACCIDENT_YEAR': df_grouped['ORIGIN_YEAR'],
        'DEVELOPMENT_DATE': df_grouped['DEVELOPMENT_DATE_PARSED'],
        'PAID': df_grouped['PAID_TL']
    })

    df_output = df_output.sort_values(['ACCIDENT_YEAR', 'DEVELOPMENT_DATE']).reset_index(drop=True)

    return df_output


def calculate_cashflow_pattern(df_formatted, scenario_name, output_dir='output'):
    """Cashflow pattern hesaplar ve Excel'e kaydeder."""
    print(f"\n  {scenario_name} için CF pattern hesaplanıyor...")

    # CF pattern hesapla
    processed_data = process_data_to_triangle(
        df_formatted,
        accident_year_column='ACCIDENT_YEAR',
        development_date_column='DEVELOPMENT_DATE',
        value_column='PAID',
        min_years=5
    )

    # Excel'e kaydet
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f'{scenario_name}.xlsx')
    export_triangle_to_excel(processed_data, output_file)

    print(f"  ✓ {output_file} kaydedildi")

    return processed_data


def create_comparison_excel(base_data, scenarios_data, output_dir='output'):
    """Base ve senaryoları karşılaştıran Excel oluşturur."""
    print("\nKarşılaştırma Excel'i oluşturuluyor...")

    output_file = os.path.join(output_dir, 'comparison_all.xlsx')

    # Base ve scenario Excel dosyalarından cashflow pattern sheet'lerini oku
    base_excel_file = os.path.join(output_dir, 'base_cashflow.xlsx')
    base_cf_pattern = pd.read_excel(base_excel_file, sheet_name='cashflow pattern')
    base_monthly_pattern = pd.read_excel(base_excel_file, sheet_name='180 aylık pattern')

    scenarios_cf_patterns = {}
    scenarios_monthly_patterns = {}
    for scenario_name in scenarios_data.keys():
        scenario_file = os.path.join(output_dir, f'scenario_{scenario_name}.xlsx')
        scenarios_cf_patterns[scenario_name] = pd.read_excel(scenario_file, sheet_name='cashflow pattern')
        scenarios_monthly_patterns[scenario_name] = pd.read_excel(scenario_file, sheet_name='180 aylık pattern')

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:

        # Sayfa 1: Kümülatif Ödeme Karşılaştırması (Yan Yana)
        base_cumulative = base_data['cumulative_data'].copy()

        # Accident year kolonu adını standartlaştır
        acc_year_col = [col for col in base_cumulative.columns if 'YEAR' in col.upper() or 'YIL' in col.upper()][0]
        base_cumulative = base_cumulative.rename(columns={acc_year_col: 'Accident_Year'})

        # Base için pivot
        df_comparison = base_cumulative[['Accident_Year', 'Development_Period', 'Cumulative_Paid']].copy()
        df_comparison = df_comparison.rename(columns={'Cumulative_Paid': 'Base_Cumulative'})

        # Her senaryo için ekle
        for scenario_name, scenario_data in scenarios_data.items():
            scenario_cumulative = scenario_data['cumulative_data'].copy()
            acc_year_col = [col for col in scenario_cumulative.columns if 'YEAR' in col.upper() or 'YIL' in col.upper()][0]
            scenario_cumulative = scenario_cumulative.rename(columns={acc_year_col: 'Accident_Year'})

            scenario_pivot = scenario_cumulative[['Accident_Year', 'Development_Period', 'Cumulative_Paid']].copy()
            scenario_pivot = scenario_pivot.rename(columns={'Cumulative_Paid': f'{scenario_name}_Cumulative'})

            # Merge
            df_comparison = df_comparison.merge(
                scenario_pivot,
                on=['Accident_Year', 'Development_Period'],
                how='outer'
            )

        # Sırala
        df_comparison = df_comparison.sort_values(['Accident_Year', 'Development_Period']).reset_index(drop=True)
        df_comparison.to_excel(writer, sheet_name='Cumulative Payments', index=False)

        # Sayfa 2: CDF Karşılaştırması
        cdf_comparison_data = []

        # Base CDF
        for period, cdf_value in base_data['cdf'].items():
            cdf_comparison_data.append({
                'Period': period,
                'Base_CDF': cdf_value
            })

        df_cdf = pd.DataFrame(cdf_comparison_data)

        # Senaryoların CDF'leri
        for scenario_name, scenario_data in scenarios_data.items():
            scenario_cdf = []
            for period, cdf_value in scenario_data['cdf'].items():
                scenario_cdf.append({
                    'Period': period,
                    f'{scenario_name}_CDF': cdf_value
                })
            df_scenario_cdf = pd.DataFrame(scenario_cdf)
            df_cdf = df_cdf.merge(df_scenario_cdf, on='Period', how='outer')

        df_cdf = df_cdf.sort_values('Period')
        df_cdf.to_excel(writer, sheet_name='CDF Comparison', index=False)

        # Sayfa 3: Çeyreklik CF Pattern Karşılaştırması (Kaza Yılı Bazlı)
        # Base pattern'i al ve senaryoları yan yana ekle
        df_cf_comparison = base_cf_pattern.copy()
        df_cf_comparison = df_cf_comparison.rename(columns={'Normalize Ağırlık': 'Base_Pattern'})

        # Her senaryo için pattern ekle
        for scenario_name, scenario_pattern in scenarios_cf_patterns.items():
            # Scenario pattern'den sadece Normalize Ağırlık sütununu al
            scenario_col = scenario_pattern[['Kaza Yılı', 'Period', 'Normalize Ağırlık']].copy()
            scenario_col = scenario_col.rename(columns={'Normalize Ağırlık': f'{scenario_name}_Pattern'})

            # Merge et
            df_cf_comparison = df_cf_comparison.merge(
                scenario_col,
                on=['Kaza Yılı', 'Period'],
                how='outer'
            )

        df_cf_comparison = df_cf_comparison.sort_values(['Kaza Yılı', 'Period']).reset_index(drop=True)
        df_cf_comparison.to_excel(writer, sheet_name='Quarterly CF Pattern', index=False)

        # Sayfa 4: Aylık CF Pattern Karşılaştırması (Kaza Yılı Bazlı)
        # Base monthly pattern'i al ve senaryoları yan yana ekle
        df_monthly_comparison = base_monthly_pattern.copy()
        df_monthly_comparison = df_monthly_comparison.rename(columns={'Normalize Ağırlık': 'Base_Monthly'})

        # Her senaryo için monthly pattern ekle
        for scenario_name, scenario_monthly in scenarios_monthly_patterns.items():
            # Scenario monthly pattern'den sadece Normalize Ağırlık sütununu al
            scenario_col = scenario_monthly[['Kaza Yılı', 'Ay', 'Normalize Ağırlık']].copy()
            scenario_col = scenario_col.rename(columns={'Normalize Ağırlık': f'{scenario_name}_Monthly'})

            # Merge et
            df_monthly_comparison = df_monthly_comparison.merge(
                scenario_col,
                on=['Kaza Yılı', 'Ay'],
                how='outer'
            )

        df_monthly_comparison = df_monthly_comparison.sort_values(['Kaza Yılı', 'Ay']).reset_index(drop=True)
        df_monthly_comparison.to_excel(writer, sheet_name='Monthly CF Pattern', index=False)

    print(f"  ✓ {output_file} kaydedildi")
    print(f"    - Cumulative Payments (yan yana)")
    print(f"    - CDF Comparison")
    print(f"    - Quarterly CF Pattern (normalize ağırlık)")
    print(f"    - Monthly CF Pattern (normalize ağırlık, aylık)")


def main():
    """Ana fonksiyon - Kullanıcı interaksiyonu."""
    print("=" * 80)
    print("CASHFLOW PATTERN SENARYO ANALİZİ")
    print("=" * 80)

    # 1. Veriyi yükle
    print("\n1. ADIM: VERİ YÜKLEME")
    print("-" * 80)
    df_original = load_and_prepare_data()

    # 2. Base cashflow hesapla
    print("\n2. ADIM: BASE CASHFLOW PATTERN")
    print("-" * 80)
    df_base = convert_to_cashflow_format(df_original)
    base_data = calculate_cashflow_pattern(df_base, 'base_cashflow')

    # 3. Senaryolar
    print("\n3. ADIM: SENARYOLAR")
    print("-" * 80)

    # Senaryo oluştur
    scenarios_data = {}

    while True:
        # Her seferinde senaryo tipini sor
        print("\nHangi tür senaryo oluşturmak istiyorsunuz?")
        print("  1) Ödeme Azaltma - Kaza Yılı Bazlı (202409 ödemeleri % azalır)")
        print("  2) Ödeme Azaltma - Dosya Bazlı (Belirli dosyalar ödenmez)")
        print("  3) Muallak Ödeme - Kaza Yılı Bazlı (202409 muallakın %'si ödenir)")
        print("  4) Muallak Ödeme - Dosya Bazlı (Belirli dosyaların muallağı ödenir)")

        while True:
            choice = input("\nSeçiminiz (1, 2, 3 veya 4): ").strip()
            if choice in ['1', '2', '3', '4']:
                break
            print("❌ Geçersiz! 1, 2, 3 veya 4 girin.")

        # Seçilen tipe göre senaryo oluştur
        if choice == '1':
            scenario_name, df_scenario = create_year_based_scenario(df_original)
        elif choice == '2':
            scenario_name, df_scenario = create_file_based_scenario(df_original)
        elif choice == '3':
            scenario_name, df_scenario = create_reserve_payment_year_scenario(df_original)
        else:
            scenario_name, df_scenario = create_reserve_payment_file_scenario(df_original)

        if scenario_name and df_scenario is not None:
            # CF pattern hesapla
            df_scenario_formatted = convert_to_cashflow_format(df_scenario)
            scenario_data = calculate_cashflow_pattern(df_scenario_formatted, f'scenario_{scenario_name}')
            scenarios_data[scenario_name] = scenario_data

        # Başka senaryo?
        another = input("\nBaşka senaryo eklemek ister misiniz? (e/h): ").strip().lower()
        if another not in ['e', 'evet', 'y', 'yes']:
            break

    # 4. Karşılaştırma Excel'i
    if scenarios_data:
        print("\n4. ADIM: KARŞILAŞTIRMA")
        print("-" * 80)
        create_comparison_excel(base_data, scenarios_data)

    # 5. Özet
    print("\n" + "=" * 80)
    print("✅ ANALİZ TAMAMLANDI!")
    print("=" * 80)
    print(f"\nOluşturulan dosyalar (output/ klasörü):")
    print(f"  1. base_cashflow.xlsx - Base pattern")
    print(f"  2. scenario_*.xlsx - {len(scenarios_data)} senaryo")
    print(f"  3. comparison_all.xlsx - Karşılaştırma (4 sheet)")
    print(f"\nToplam: {2 + len(scenarios_data)} Excel dosyası")


def create_year_based_scenario(df_original):
    """Kaza yılı bazlı senaryo oluşturur (sadece MB_FINAL='Bodily' dosyalara uygulanır)."""
    print("\n" + "=" * 80)
    print("KAZA YILI BAZLI SENARYO")
    print("=" * 80)
    print("Not: Sadece MB_FINAL='Bodily' olan dosyalara uygulanır")

    # Senaryo adı
    scenario_name = input("\nSenaryo adı: ").strip()
    if not scenario_name:
        scenario_name = f"year_scenario_{pd.Timestamp.now().strftime('%H%M%S')}"

    # Kaza yılları
    print("\nKaza yılları (virgülle ayırın, örn: 2023,2024 veya 2020-2022):")
    years_input = input("Yıllar: ").strip()

    try:
        if '-' in years_input and ',' not in years_input:
            start, end = years_input.split('-')
            years = list(range(int(start), int(end) + 1))
        elif ',' in years_input:
            years = [int(y.strip()) for y in years_input.split(',')]
        else:
            years = [int(years_input)]
    except:
        print("❌ Geçersiz format!")
        return None, None

    # Azaltma oranı
    while True:
        try:
            reduction = float(input("Azaltma oranı (%): ").strip())
            if 0 <= reduction <= 100:
                break
        except:
            pass
        print("❌ 0-100 arası sayı girin!")

    # Senaryo datasını oluştur
    df_scenario = df_original.copy()

    # Sadece MB_FINAL = 'Bodily' olan dosyalara filtre uygula
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['ORIGIN_YEAR'].isin(years)) &
        (df_scenario['MB_FINAL'] == 'Bodily')
    )
    affected_rows = condition.sum()
    total_amount = df_scenario.loc[condition, 'PAID_TL'].sum()

    df_scenario.loc[condition, 'PAID_TL'] = df_scenario.loc[condition, 'PAID_TL'] * (1 - reduction / 100)

    print(f"\n✓ Yıllar {years} -> %{reduction} azaltma (sadece Bodily)")
    print(f"✓ Etkilenen satır: {affected_rows:,}")
    print(f"✓ Etkilenen tutar: {total_amount:,.2f} TL")

    return scenario_name, df_scenario


def create_file_based_scenario(df_original):
    """Dosya (CLAIM_NO) bazlı senaryo oluşturur."""
    print("\n" + "=" * 80)
    print("DOSYA (CLAIM_NO) BAZLI SENARYO")
    print("=" * 80)

    # Senaryo adı
    scenario_name = input("\nSenaryo adı: ").strip()
    if not scenario_name:
        scenario_name = f"file_scenario_{pd.Timestamp.now().strftime('%H%M%S')}"

    # CLAIM_NO'ları al
    print("\nDosya numaralarını girin (virgülle ayırın):")
    print("Örnek: 500019,500036,500045")

    claim_input = input("CLAIM_NO'lar: ").strip()

    if not claim_input:
        print("❌ Hiç dosya girilmedi!")
        return None, None

    claim_numbers = [cn.strip() for cn in claim_input.split(',')]

    # Senaryo datasını oluştur
    df_scenario = df_original.copy()
    condition = (df_scenario['YEARMONTH'] == 202409) & (df_scenario['CLAIM_NO'].isin(claim_numbers))
    affected_rows = condition.sum()
    total_amount = df_scenario.loc[condition, 'PAID_TL'].sum()

    df_scenario.loc[condition, 'PAID_TL'] = 0  # Sıfırla

    print(f"\n✓ {len(claim_numbers)} dosya için 202409 ödemeleri sıfırlandı")
    print(f"✓ Etkilenen satır: {affected_rows:,}")
    print(f"✓ Sıfırlanan tutar: {total_amount:,.2f} TL")

    return scenario_name, df_scenario


def create_reserve_payment_year_scenario(df_original):
    """Kaza yılı bazlı muallak ödeme senaryosu (202409 muallakın %'si ödenir, sadece Bodily)."""
    print("\n" + "=" * 80)
    print("MUALLAK ÖDEME - KAZA YILI BAZLI SENARYO")
    print("=" * 80)
    print("Not: 202409'daki muallakın (OS_TL) %'si ödemeye eklenir")
    print("     Sadece MB_FINAL='Bodily' olan dosyalara uygulanır")

    # Senaryo adı
    scenario_name = input("\nSenaryo adı: ").strip()
    if not scenario_name:
        scenario_name = f"reserve_year_{pd.Timestamp.now().strftime('%H%M%S')}"

    # Kaza yılları
    print("\nKaza yılları (virgülle ayırın, örn: 2023,2024 veya 2020-2022):")
    years_input = input("Yıllar: ").strip()

    try:
        if '-' in years_input and ',' not in years_input:
            start, end = years_input.split('-')
            years = list(range(int(start), int(end) + 1))
        elif ',' in years_input:
            years = [int(y.strip()) for y in years_input.split(',')]
        else:
            years = [int(years_input)]
    except:
        print("❌ Geçersiz format!")
        return None, None

    # Ödeme oranı
    while True:
        try:
            payment_pct = float(input("Muallakın yüzde kaçı ödensin? (%): ").strip())
            if 0 <= payment_pct <= 100:
                break
        except:
            pass
        print("❌ 0-100 arası sayı girin!")

    # Senaryo datasını oluştur
    df_scenario = df_original.copy()

    # Sadece MB_FINAL = 'Bodily' olan dosyalara filtre uygula
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['ORIGIN_YEAR'].isin(years)) &
        (df_scenario['MB_FINAL'] == 'Bodily')
    )
    affected_rows = condition.sum()

    # OS_TL'nin %'sini PAID_TL'ye ekle ve OS_TL'yi azalt
    reserve_amount = df_scenario.loc[condition, 'OS_TL'].sum()
    payment_addition = reserve_amount * (payment_pct / 100)

    # Ödenen kısmı PAID_TL'ye ekle
    df_scenario.loc[condition, 'PAID_TL'] = (
        df_scenario.loc[condition, 'PAID_TL'] +
        df_scenario.loc[condition, 'OS_TL'] * (payment_pct / 100)
    )

    # Ödenen kısmı OS_TL'den çıkar
    df_scenario.loc[condition, 'OS_TL'] = (
        df_scenario.loc[condition, 'OS_TL'] * (1 - payment_pct / 100)
    )

    print(f"\n✓ Yıllar {years} -> Muallakın %{payment_pct}'i ödendi (sadece Bodily)")
    print(f"✓ Etkilenen satır: {affected_rows:,}")
    print(f"✓ Toplam muallak (OS_TL): {reserve_amount:,.2f} TL")
    print(f"✓ Ödemeye eklenen tutar: {payment_addition:,.2f} TL")

    return scenario_name, df_scenario


def create_reserve_payment_file_scenario(df_original):
    """Dosya bazlı muallak ödeme senaryosu (202409 muallak tamamen ödenir)."""
    print("\n" + "=" * 80)
    print("MUALLAK ÖDEME - DOSYA BAZLI SENARYO")
    print("=" * 80)
    print("Not: Seçilen dosyaların 202409'daki muallağı (OS_TL) tamamen ödenir")

    # Senaryo adı
    scenario_name = input("\nSenaryo adı: ").strip()
    if not scenario_name:
        scenario_name = f"reserve_file_{pd.Timestamp.now().strftime('%H%M%S')}"

    # CLAIM_NO'ları al
    print("\nDosya numaralarını girin (virgülle ayırın):")
    print("Örnek: 500019,500036,500045")

    claim_input = input("CLAIM_NO'lar: ").strip()

    if not claim_input:
        print("❌ Hiç dosya girilmedi!")
        return None, None

    claim_numbers = [cn.strip() for cn in claim_input.split(',')]

    # Senaryo datasını oluştur
    df_scenario = df_original.copy()
    condition = (df_scenario['YEARMONTH'] == 202409) & (df_scenario['CLAIM_NO'].isin(claim_numbers))
    affected_rows = condition.sum()
    reserve_amount = df_scenario.loc[condition, 'OS_TL'].sum()

    # OS_TL'yi tamamen PAID_TL'ye ekle
    df_scenario.loc[condition, 'PAID_TL'] = (
        df_scenario.loc[condition, 'PAID_TL'] +
        df_scenario.loc[condition, 'OS_TL']
    )

    # OS_TL'yi sıfırla (tamamen ödendi)
    df_scenario.loc[condition, 'OS_TL'] = 0

    print(f"\n✓ {len(claim_numbers)} dosya için 202409 muallakları ödendi")
    print(f"✓ Etkilenen satır: {affected_rows:,}")
    print(f"✓ Ödenen muallak tutarı: {reserve_amount:,.2f} TL")

    return scenario_name, df_scenario


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Program kullanıcı tarafından sonlandırıldı.")
    except Exception as e:
        print(f"\n❌ Hata: {e}")
        import traceback
        traceback.print_exc()
