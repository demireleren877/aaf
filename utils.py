"""
Yardımcı fonksiyonlar modülü.
"""

import pandas as pd
import numpy as np
from typing import Dict
from datetime import datetime
from triangle_processor import calculate_development_period_from_date


def export_triangle_to_excel(processed_data: Dict, output_path: str):
    """
    Üçgen matris ve sonuçları Excel'e kaydeder (4 sayfa).
    
    Args:
        processed_data: process_data_to_triangle fonksiyonunun sonucu
        output_path: Çıktı dosya yolu
    """
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sayfa 1: Orijinal Data
        original_df = processed_data['original_data'].copy()
        original_df.to_excel(writer, sheet_name='data', index=False)
        
        # Sayfa 2: Kümül Data
        cumulative_df = processed_data['cumulative_data'].copy()
        cumulative_df.to_excel(writer, sheet_name='kümül data', index=False)
        
        # Sayfa 3: Üçgen Matris
        triangle_df = processed_data['triangle_df'].copy()
        # NaN değerleri boş string'e çevir (daha temiz görünüm için)
        triangle_df_display = triangle_df.copy()
        triangle_df_display = triangle_df_display.fillna('')
        triangle_df_display.to_excel(writer, sheet_name='üçgen', index=True)
        
        # Sayfa 4: Dev Factorleri
        dev_factors_list = []
        cdf_dict = processed_data.get('cdf', {})
        
        # Rapor tarihini belirle: en son development date'ten
        original_data = processed_data.get('original_data', pd.DataFrame())
        dev_date_col = None
        accident_col = None
        
        for col in original_data.columns:
            col_upper = col.upper().replace(' ', '_')
            if 'DEVELOPMENT' in col_upper and 'DATE' in col_upper:
                dev_date_col = col
            elif 'ACCIDENT' in col_upper and ('YEA' in col_upper or 'YEAR' in col_upper):
                accident_col = col
        
        report_period = None
        if dev_date_col is not None and accident_col is not None and not original_data.empty:
            # En son development date'i bul
            max_dev_date = pd.to_datetime(original_data[dev_date_col], errors='coerce').max()
            if pd.notna(max_dev_date):
                # En son development date'in olduğu satırları bul
                max_date_rows = original_data[pd.to_datetime(original_data[dev_date_col], errors='coerce') == max_dev_date]
                if not max_date_rows.empty:
                    # En son development date'in period'unu hesapla
                    # Farklı accident year'lar için farklı period'lar olabilir, en yüksek period'u al
                    max_period = 0
                    for _, row in max_date_rows.iterrows():
                        try:
                            period = calculate_development_period_from_date(
                                row[accident_col],
                                row[dev_date_col]
                            )
                            max_period = max(max_period, period)
                        except:
                            pass
                    report_period = max_period
        
        # Period'ları sıralı al
        periods = sorted(processed_data['dev_factors'].keys())
        
        # Rapor tarihinden sonraki period'ları belirle
        # Kullanıcı "0,1,2. dev periodları almayacağız" dedi, yani period >= 3 olanları alacağız
        if report_period is not None:
            # Rapor tarihinden sonraki period'lar (report_period'dan büyük olanlar)
            future_periods = [p for p in periods if p > report_period]
        else:
            # Rapor tarihi belirlenemezse, period >= 3 olanları al (güvenli varsayılan)
            # 2025Q3 datası için period 0,1,2'yi almayacağız, period 3'ten başlayacağız
            future_periods = [p for p in periods if p >= 3]
        
        # 100/CDF değerlerini hesapla
        inv_cdf_100_dict = {}
        for period in periods:
            factor_data = processed_data['dev_factors'][period]
            cdf_value = cdf_dict.get(period, None)
            
            # 100/CDF hesapla
            inv_cdf_100 = 100.0 / cdf_value if cdf_value is not None and cdf_value != 0 else None
            inv_cdf_100_dict[period] = inv_cdf_100
        
        # 100/CDF'nin incrementali hesapla (bir önceki değerden fark)
        inv_cdf_100_incremental_dict = {}
        for i, period in enumerate(periods):
            inv_cdf_100 = inv_cdf_100_dict.get(period)
            if i == 0:
                # İlk değer için incremental = kendisi
                inv_cdf_100_incremental_dict[period] = inv_cdf_100
            else:
                # Bir önceki değerden fark
                prev_period = periods[i-1]
                prev_val = inv_cdf_100_dict.get(prev_period)
                curr_val = inv_cdf_100
                if pd.notna(prev_val) and pd.notna(curr_val):
                    inv_cdf_100_incremental_dict[period] = curr_val - prev_val
                else:
                    inv_cdf_100_incremental_dict[period] = None
        
        # 0, 1, 2 dev period'lar hariç, period >= 3 ve period < 60 olanları al
        periods_for_weight = [p for p in periods if p >= 3 and p < 60]
        
        # Period >= 3 ve period < 60 olanlar için 100/CDF incrementali toplamı bul
        total_inv_cdf_100_incremental = 0
        for period in periods_for_weight:
            inv_cdf_100_inc = inv_cdf_100_incremental_dict.get(period)
            if inv_cdf_100_inc is not None and not np.isnan(inv_cdf_100_inc):
                total_inv_cdf_100_incremental += inv_cdf_100_inc
        
        # Ağırlıkları hesapla: (100/CDF incremental) / (tüm incrementalleri toplamı)
        # İlk 60 period için (0-59), sonrası 0
        weights_dict = {}
        for period in periods:
            if period >= 3 and period < 60:  # 0, 1, 2 hariç ve ilk 60 period
                inv_cdf_100_inc = inv_cdf_100_incremental_dict.get(period)
                if inv_cdf_100_inc is not None and not np.isnan(inv_cdf_100_inc) and total_inv_cdf_100_incremental != 0:
                    weights_dict[period] = inv_cdf_100_inc / total_inv_cdf_100_incremental
                else:
                    weights_dict[period] = None
            elif period >= 60:
                weights_dict[period] = 0.0  # Period >= 60 için 0
            else:
                weights_dict[period] = None  # Period 0, 1, 2 için None
        
        # Ağırlıkların normalize edilmiş versiyonları (kendi içinde)
        # Period >= 3 ve period < 60 olanlar için toplamı bul
        sum_weights = sum(w for w in weights_dict.values() if w is not None and not np.isnan(w))
        normalized_weights_dict = {}
        for period in periods:
            if period >= 3 and period < 60:  # 0, 1, 2 hariç ve ilk 60 period
                weight = weights_dict.get(period)
                if weight is not None and not np.isnan(weight) and sum_weights != 0:
                    normalized_weights_dict[period] = weight / sum_weights
                else:
                    normalized_weights_dict[period] = None
            elif period >= 60:
                normalized_weights_dict[period] = 0.0  # Period >= 60 için 0
            else:
                normalized_weights_dict[period] = None  # Period 0, 1, 2 için None
        
        for period in periods:
            factor_data = processed_data['dev_factors'][period]
            cdf_value = cdf_dict.get(period, None)
            
            # 100/CDF hesapla
            inv_cdf_100 = inv_cdf_100_dict.get(period)
            inv_cdf_100_incremental = inv_cdf_100_incremental_dict.get(period)
            
            dev_factors_list.append({
                'Development Period': period,
                'Development Factor': factor_data['factor'],
                'Kullanılan Yıllar': ', '.join(map(str, factor_data['used_years'])),
                'Toplam (Current Period)': factor_data['sum_current'],
                'Toplam (Next Period)': factor_data['sum_next'],
                'CDF': cdf_value,
                '100/CDF': inv_cdf_100,
                '100/CDF Incremental': inv_cdf_100_incremental,
                'Ağırlık (100/CDF Incremental)': weights_dict.get(period),
                'Normalize Ağırlık': normalized_weights_dict.get(period)
            })
        
        dev_factors_df = pd.DataFrame(dev_factors_list)
        dev_factors_df.to_excel(writer, sheet_name='dev factorleri', index=False)
        
        # Sayfa 5: Her Kaza Yılı İçin Normalize Ağırlık (Cashflow Pattern)
        triangle_df = processed_data['triangle_df'].copy()
        years = sorted(triangle_df.index.tolist())
        
        # Rapor tarihini belirle (en son development date'ten)
        report_date = None
        if dev_date_col is not None and not original_data.empty:
            report_date = pd.to_datetime(original_data[dev_date_col], errors='coerce').max()
        
        # Her kaza yılı için rapor tarihindeki period'u hesapla
        year_excluded_periods = {}  # Her yıl için hariç tutulacak period sayısı
        if report_date is not None and pd.notna(report_date) and accident_col is not None:
            for year in years:
                try:
                    # Bu yıl için rapor tarihindeki period'u hesapla
                    year_period = calculate_development_period_from_date(year, report_date)
                    # İlk N period hariç tutulacak (N = rapor tarihindeki period + 1)
                    year_excluded_periods[year] = year_period + 1
                except:
                    # Hesaplanamazsa varsayılan değerler kullan
                    if year == max(years):  # En yeni yıl
                        year_excluded_periods[year] = 3  # 2024 için 3 period
                    elif year == max(years) - 1:  # Bir önceki yıl
                        year_excluded_periods[year] = 7  # 2023 için 7 period
                    elif year == max(years) - 2:  # İki önceki yıl
                        year_excluded_periods[year] = 11  # 2022 için 11 period
                    else:
                        year_excluded_periods[year] = 3  # Varsayılan
        else:
            # Rapor tarihi belirlenemezse varsayılan değerler
            for i, year in enumerate(years):
                if i == len(years) - 1:  # En yeni yıl
                    year_excluded_periods[year] = 3
                elif i == len(years) - 2:  # Bir önceki yıl
                    year_excluded_periods[year] = 7
                elif i == len(years) - 3:  # İki önceki yıl
                    year_excluded_periods[year] = 11
                else:
                    year_excluded_periods[year] = 3
        
        # Her kaza yılı için normalize ağırlık sütunu oluştur
        # Her yıl için kendi içinde normalize et (toplam 1 olsun)
        # Format: Kaza Yılı | Period (1-60) | Normalize Ağırlık (satır satır)
        # Period'lar sıralı: 1. period = ilk oran, 2. period = ikinci oran, ...
        
        # Her kaza yılı için hariç tutulmayan development period'ları topla ve normalize et
        cashflow_pattern_list = []
        for year in years:
            excluded_count = year_excluded_periods.get(year, 3)
            
            # Bu yıl için hariç tutulmayan development period'ların normalize ağırlıklarını topla
            included_weights = []
            for period in periods:
                if period >= excluded_count:
                    normalized_weight = normalized_weights_dict.get(period)
                    if normalized_weight is not None and not np.isnan(normalized_weight):
                        included_weights.append(normalized_weight)
            
            # Toplamı bul
            weight_sum = sum(included_weights) if included_weights else 0
            
            # Eğer hiç veri yoksa, 1. period'da 100% yap
            if weight_sum == 0:
                for seq_period in range(1, 61):  # 1-60
                    normalize_weight = 1.0 if seq_period == 1 else 0.0
                    cashflow_pattern_list.append({
                        'Kaza Yılı': year,
                        'Period': seq_period,
                        'Normalize Ağırlık': normalize_weight
                    })
            else:
                # Normalize ağırlıkları sıralı period'lara eşle (1-60)
                seq_period = 1
                for period in periods:
                    if period >= excluded_count:
                        normalized_weight = normalized_weights_dict.get(period)
                        if normalized_weight is not None and not np.isnan(normalized_weight):
                            if seq_period <= 60:  # Maksimum 60 period
                                # Bu yıl için kendi içinde normalize et (toplam 1 olsun)
                                normalize_weight = normalized_weight / weight_sum
                                cashflow_pattern_list.append({
                                    'Kaza Yılı': year,
                                    'Period': seq_period,
                                    'Normalize Ağırlık': normalize_weight
                                })
                                seq_period += 1
                
                # Eğer 60 period'a ulaşmadıysak, kalan period'ları 0 ile doldur
                while seq_period <= 60:
                    cashflow_pattern_list.append({
                        'Kaza Yılı': year,
                        'Period': seq_period,
                        'Normalize Ağırlık': 0.0
                    })
                    seq_period += 1
        
        cashflow_pattern_df = pd.DataFrame(cashflow_pattern_list)
        cashflow_pattern_df.to_excel(writer, sheet_name='cashflow pattern', index=False)
        
        # Sayfa 6: 180 Aylık Pattern (Her period oranını 3'e bölerek)
        # Format: Kaza Yılı | Ay (1-180) | Normalize Ağırlık
        monthly_pattern_list = []
        for year in years:
            # Bu yıl için period pattern'ini al
            year_periods = cashflow_pattern_df[cashflow_pattern_df['Kaza Yılı'] == year]
            
            for seq_period in range(1, 61):  # 1-60 period
                period_row = year_periods[year_periods['Period'] == seq_period]
                if not period_row.empty:
                    period_weight = period_row['Normalize Ağırlık'].iloc[0]
                    if period_weight is not None and not np.isnan(period_weight):
                        # Her period'u 3 aya böl
                        monthly_weight = period_weight / 3.0
                        # Bu period için 3 ay oluştur
                        for month_in_period in range(3):
                            month_number = (seq_period - 1) * 3 + month_in_period + 1  # 1-180
                            if month_number <= 180:
                                monthly_pattern_list.append({
                                    'Kaza Yılı': year,
                                    'Ay': month_number,
                                    'Normalize Ağırlık': monthly_weight
                                })
                    else:
                        # Period weight 0 veya None ise, 3 ay için de 0
                        for month_in_period in range(3):
                            month_number = (seq_period - 1) * 3 + month_in_period + 1  # 1-180
                            if month_number <= 180:
                                monthly_pattern_list.append({
                                    'Kaza Yılı': year,
                                    'Ay': month_number,
                                    'Normalize Ağırlık': 0.0
                                })
                else:
                    # Period bulunamadıysa, 3 ay için 0
                    for month_in_period in range(3):
                        month_number = (seq_period - 1) * 3 + month_in_period + 1  # 1-180
                        if month_number <= 180:
                            monthly_pattern_list.append({
                                'Kaza Yılı': year,
                                'Ay': month_number,
                                'Normalize Ağırlık': 0.0
                            })
        
        monthly_pattern_df = pd.DataFrame(monthly_pattern_list)
        monthly_pattern_df.to_excel(writer, sheet_name='180 aylık pattern', index=False)

