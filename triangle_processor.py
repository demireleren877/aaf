"""
Üçgen matris işleme modülü.
Veriyi kümülatif hale getirir, üçgen matris oluşturur ve dev factor'leri hesaplar.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime


def calculate_development_period_from_date(accident_year, development_date):
    """
    DEVELOPMENT_DATE'den development period hesaplar.
    Tarih formatı: DD.MM.YYYY (ör: 01.01.2010, 01.04.2010)
    """
    if isinstance(development_date, str):
        try:
            dev_date = datetime.strptime(development_date, '%d.%m.%Y')
        except ValueError:
            dev_date = pd.to_datetime(development_date)
    elif isinstance(development_date, datetime):
        dev_date = development_date
    elif isinstance(development_date, pd.Timestamp):
        dev_date = development_date.to_pydatetime()
    else:
        raise ValueError(f"Geçersiz tarih tipi: {type(development_date)}")
    
    acc_year = int(accident_year)
    month = dev_date.month
    
    if month in [1, 4, 7, 10]:
        year_diff = dev_date.year - acc_year
        quarter = (month - 1) // 3
        development_period = year_diff * 4 + quarter
    else:
        development_period = dev_date.year - acc_year
    
    return max(0, development_period)


def prepare_cumulative_data(df: pd.DataFrame,
                           accident_year_column: str,
                           development_date_column: str,
                           value_column: str) -> pd.DataFrame:
    """
    Veriyi kaza yılı ve period'a göre kümülatif hale getirir.
    
    Args:
        df: Ham veri DataFrame'i
        accident_year_column: Accident year sütunu adı
        development_date_column: Development date sütunu adı
        value_column: Değer (hasar) sütunu adı
    
    Returns:
        Kümülatif DataFrame
    """
    df_processed = df.copy()
    
    # Development period hesapla
    df_processed['Development_Period'] = df_processed.apply(
        lambda row: calculate_development_period_from_date(
            row[accident_year_column],
            row[development_date_column]
        ),
        axis=1
    )
    
    # Kaza yılı ve period'a göre grupla ve topla (incremental tutarları topla)
    incremental_df = df_processed.groupby([accident_year_column, 'Development_Period'])[value_column].sum().reset_index()
    incremental_df = incremental_df.rename(columns={value_column: 'Incremental_Paid'})
    
    # Her kaza yılı için period'lara göre kümülatif hale getir
    cumulative_data = []
    for year in sorted(incremental_df[accident_year_column].unique()):
        year_data = incremental_df[incremental_df[accident_year_column] == year].copy()
        year_data = year_data.sort_values('Development_Period')
        
        cumulative_sum = 0
        for _, row in year_data.iterrows():
            cumulative_sum += row['Incremental_Paid']
            cumulative_data.append({
                accident_year_column: year,
                'Development_Period': row['Development_Period'],
                'Cumulative_Paid': cumulative_sum
            })
    
    return pd.DataFrame(cumulative_data)


def create_triangle_matrix(cumulative_df: pd.DataFrame,
                          accident_year_column: str,
                          value_column: str = 'Cumulative_Paid') -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Kümülatif veriden üçgen matris oluşturur.
    Satırlar: Kaza yılları
    Sütunlar: Development period'lar
    
    Args:
        cumulative_df: Kümülatif DataFrame
        accident_year_column: Accident year sütunu adı
        value_column: Değer sütunu adı
    
    Returns:
        (DataFrame formatında üçgen, NumPy array formatında üçgen)
    """
    years = sorted(cumulative_df[accident_year_column].unique())
    periods = sorted(cumulative_df['Development_Period'].unique())
    
    # Üçgen matris DataFrame'i oluştur
    triangle_df = pd.DataFrame(index=years, columns=periods)
    
    # Üçgen matrisi doldur
    for _, row in cumulative_df.iterrows():
        year = row[accident_year_column]
        period = row['Development_Period']
        value = row[value_column]
        
        if year in triangle_df.index and period in triangle_df.columns:
            triangle_df.loc[year, period] = value
    
    # NumPy array'e çevir
    triangle_array = triangle_df.values
    
    return triangle_df, triangle_array


def calculate_development_factors_last5years(triangle_df: pd.DataFrame,
                                            triangle_array: np.ndarray,
                                            min_years: int = 5) -> Dict[int, Dict]:
    """
    Development factor'leri son 5 yılın toplamını kullanarak hesaplar.
    
    Args:
        triangle_df: Üçgen matris DataFrame (satır: yıllar, sütun: period'lar)
        triangle_array: Üçgen matris NumPy array
        min_years: Kullanılacak minimum yıl sayısı (varsayılan: 5)
    
    Returns:
        Her period için:
        {
            period: {
                'factor': float,
                'used_years': list,
                'sum_current': float,
                'sum_next': float
            }
        }
    """
    years = triangle_df.index.tolist()
    periods = triangle_df.columns.tolist()
    
    dev_factors = {}
    
    # Her period için (son period hariç)
    for period_idx in range(len(periods) - 1):
        current_period = periods[period_idx]
        next_period = periods[period_idx + 1]
        
        # Her iki period'da da veri olan yılları bul
        valid_years = []
        for year in years:
            current_val = triangle_df.loc[year, current_period]
            next_val = triangle_df.loc[year, next_period]
            
            if pd.notna(current_val) and pd.notna(next_val) and current_val != 0:
                valid_years.append(year)
        
        if len(valid_years) == 0:
            dev_factors[current_period] = {
                'factor': np.nan,
                'used_years': [],
                'sum_current': 0,
                'sum_next': 0
            }
            continue
        
        # Son N yılın verilerini kullan (eğer yeterli yıl varsa)
        valid_years_sorted = sorted(valid_years, reverse=True)
        years_to_use = valid_years_sorted[:min_years] if len(valid_years_sorted) >= min_years else valid_years_sorted
        
        # Seçilen yılların toplamını hesapla
        sum_current = 0
        sum_next = 0
        
        for year in years_to_use:
            current_val = triangle_df.loc[year, current_period]
            next_val = triangle_df.loc[year, next_period]
            
            if pd.notna(current_val) and pd.notna(next_val):
                sum_current += float(current_val)
                sum_next += float(next_val)
        
        # Development factor hesapla
        if sum_current > 0:
            factor = sum_next / sum_current
        else:
            factor = np.nan
        
        dev_factors[current_period] = {
            'factor': factor,
            'used_years': sorted(years_to_use),
            'sum_current': sum_current,
            'sum_next': sum_next
        }
    
    return dev_factors


def calculate_cdf_from_dev_factors(dev_factors: Dict[int, Dict],
                                   periods: list) -> Dict[int, float]:
    """
    Development factor'lerden CDF hesaplar.
    
    Args:
        dev_factors: Development factor dictionary'si
        periods: Development period listesi
    
    Returns:
        Her period için CDF değerleri
    """
    cdf = {}
    
    # Son period için CDF = 1.0
    last_period = periods[-1]
    cdf[last_period] = 1.0
    
    # Geriye doğru CDF hesapla
    for i in range(len(periods) - 2, -1, -1):
        current_period = periods[i]
        next_period = periods[i + 1]
        
        if current_period in dev_factors:
            factor = dev_factors[current_period]['factor']
            if not np.isnan(factor):
                cdf[current_period] = factor * cdf[next_period]
            else:
                cdf[current_period] = cdf[next_period]
        else:
            cdf[current_period] = cdf[next_period]
    
    return cdf


def process_data_to_triangle(df: pd.DataFrame,
                             accident_year_column: str,
                             development_date_column: str,
                             value_column: str,
                             min_years: int = 5) -> Dict:
    """
    Veriyi işleyip üçgen matris ve dev factor'leri oluşturur.
    
    Args:
        df: Ham veri DataFrame'i
        accident_year_column: Accident year sütunu adı
        development_date_column: Development date sütunu adı
        value_column: Değer sütunu adı
        min_years: Dev factor hesaplamada kullanılacak yıl sayısı
    
    Returns:
        {
            'original_data': DataFrame,
            'cumulative_data': DataFrame,
            'triangle_df': DataFrame,
            'triangle_array': np.ndarray,
            'dev_factors': Dict,
            'cdf': Dict
        }
    """
    # 1. Orijinal veri
    original_data = df.copy()
    
    # 2. Kümülatif veri hazırla
    cumulative_data = prepare_cumulative_data(
        df,
        accident_year_column,
        development_date_column,
        value_column
    )
    
    # 3. Üçgen matris oluştur
    triangle_df, triangle_array = create_triangle_matrix(
        cumulative_data,
        accident_year_column,
        'Cumulative_Paid'
    )
    
    # 4. Development factor'leri hesapla (son 5 yıl)
    dev_factors = calculate_development_factors_last5years(
        triangle_df,
        triangle_array,
        min_years
    )
    
    # 5. CDF hesapla
    periods = triangle_df.columns.tolist()
    cdf = calculate_cdf_from_dev_factors(dev_factors, periods)
    
    return {
        'original_data': original_data,
        'cumulative_data': cumulative_data,
        'triangle_df': triangle_df,
        'triangle_array': triangle_array,
        'dev_factors': dev_factors,
        'cdf': cdf,
        'periods': periods,
        'years': triangle_df.index.tolist()
    }

