"""
Flask Web Application - Cashflow Pattern Scenario Analysis
Modern, kullanıcı dostu arayüz
"""
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
import pandas as pd
import os
import json
import uuid
import threading
from datetime import datetime
from main import (
    load_and_prepare_data,
    convert_to_cashflow_format,
    calculate_cashflow_pattern,
    create_comparison_excel
)
from oracle_connector import oracle_db
from analysis_engine import script_manager, analysis_engine

app = Flask(__name__)
app.secret_key = 'cashflow_analysis_secret_key_2024'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Global state
OUTPUT_DIR = 'output'
UPLOAD_DIR = 'uploads'
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Store the current data file path and dataframe in memory
current_data = {
    'file_path': None,
    'df': None
}

# Oracle load jobs (background): job_id -> { status, result?, error? }
oracle_load_jobs = {}


@app.route('/')
def index():
    """Ana sayfa"""
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Dosya yükle"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Dosya seçilmedi'}), 400

        # Dosya uzantısı kontrolü
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Sadece CSV veya Excel dosyaları kabul edilir'}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_DIR, filename)
        file.save(file_path)

        # Store file path for later use
        current_data['file_path'] = file_path

        return jsonify({
            'success': True,
            'message': f'Dosya yüklendi: {filename}',
            'filename': filename
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/load-data', methods=['POST'])
def load_data():
    """Veriyi yükle ve base cashflow hesapla"""
    try:
        # Session temizle
        session.clear()

        # Check if we have an uploaded file or use default
        file_path = current_data.get('file_path')
        if file_path and os.path.exists(file_path):
            df_original = load_and_prepare_data(file_path)
        else:
            df_original = load_and_prepare_data()

        # Store dataframe in memory
        current_data['df'] = df_original

        # Base cashflow hesapla
        df_base = convert_to_cashflow_format(df_original)
        base_data = calculate_cashflow_pattern(df_base, 'base_cashflow', OUTPUT_DIR)

        # Özet bilgileri
        total_rows = len(df_original)
        unique_claims = df_original['CLAIM_NO'].nunique()
        years = sorted(df_original['ORIGIN_YEAR'].unique().tolist())

        # 202409 özet
        df_202409 = df_original[df_original['YEARMONTH'] == 202409]
        total_paid_202409 = df_202409['PAID_TL'].sum()
        total_os_202409 = df_202409['OS_TL'].sum()

        # Session'a kaydet
        session['data_loaded'] = True
        session['scenarios'] = []

        return jsonify({
            'success': True,
            'message': 'Veri başarıyla yüklendi ve base cashflow hesaplandı',
            'stats': {
                'total_rows': total_rows,
                'unique_claims': unique_claims,
                'years': years,
                'total_paid_202409': float(total_paid_202409),
                'total_os_202409': float(total_os_202409),
                'base_file': 'base_cashflow.xlsx'
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/data/table', methods=['GET'])
def get_data_table():
    """Veri tablosu için paginated data döndür"""
    try:
        df = current_data.get('df')
        if df is None:
            return jsonify({'success': False, 'error': 'Veri yüklenmemiş'}), 400

        # Pagination parametreleri
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '', type=str)
        year_filter = request.args.get('year', '', type=str)
        mb_filter = request.args.get('mb_final', '', type=str)

        # Filter data
        filtered_df = df.copy()

        if search:
            filtered_df = filtered_df[
                filtered_df['CLAIM_NO'].astype(str).str.contains(search, case=False, na=False)
            ]

        if year_filter:
            filtered_df = filtered_df[filtered_df['ORIGIN_YEAR'] == int(year_filter)]

        if mb_filter:
            filtered_df = filtered_df[filtered_df['MB_FINAL'] == mb_filter]

        # Only 202409 data for scenarios
        df_202409 = filtered_df[filtered_df['YEARMONTH'] == 202409].copy()

        # Aggregate by CLAIM_NO for display
        df_grouped = df_202409.groupby('CLAIM_NO').agg({
            'ORIGIN_YEAR': 'first',
            'MB_FINAL': 'first',
            'PAID_TL': 'sum',
            'OS_TL': 'sum'
        }).reset_index()

        total_records = len(df_grouped)
        total_pages = (total_records + per_page - 1) // per_page

        # Pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_data = df_grouped.iloc[start_idx:end_idx]

        # Convert to records
        records = page_data.to_dict('records')

        # Format numbers for display
        for r in records:
            r['PAID_TL_FORMATTED'] = f"{r['PAID_TL']:,.2f}"
            r['OS_TL_FORMATTED'] = f"{r['OS_TL']:,.2f}"

        return jsonify({
            'success': True,
            'data': records,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages
            },
            'filters': {
                'years': sorted(df['ORIGIN_YEAR'].unique().tolist()),
                'mb_finals': sorted(df['MB_FINAL'].dropna().unique().tolist())
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/data/claims/search', methods=['GET'])
def search_claims():
    """Claim numarası ara - autocomplete için"""
    try:
        df = current_data.get('df')
        if df is None:
            return jsonify({'success': False, 'error': 'Veri yüklenmemiş'}), 400

        query = request.args.get('q', '', type=str)
        limit = request.args.get('limit', 20, type=int)

        # 202409 data
        df_202409 = df[df['YEARMONTH'] == 202409]

        # Group by claim
        df_grouped = df_202409.groupby('CLAIM_NO').agg({
            'ORIGIN_YEAR': 'first',
            'MB_FINAL': 'first',
            'PAID_TL': 'sum',
            'OS_TL': 'sum'
        }).reset_index()

        if query:
            df_filtered = df_grouped[
                df_grouped['CLAIM_NO'].astype(str).str.contains(query, case=False, na=False)
            ]
        else:
            df_filtered = df_grouped

        # Sort by OS_TL descending (biggest reserves first) and limit
        df_filtered = df_filtered.sort_values('OS_TL', ascending=False).head(limit)

        claims = df_filtered.to_dict('records')
        for c in claims:
            c['PAID_TL_FORMATTED'] = f"{c['PAID_TL']:,.2f}"
            c['OS_TL_FORMATTED'] = f"{c['OS_TL']:,.2f}"

        return jsonify({
            'success': True,
            'claims': claims
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scenarios', methods=['GET'])
def get_scenarios():
    """Tüm senaryoları listele"""
    scenarios = session.get('scenarios', [])
    return jsonify({
        'success': True,
        'scenarios': scenarios
    })


@app.route('/api/scenario/create', methods=['POST'])
def create_scenario():
    """Yeni senaryo oluştur"""
    try:
        data = request.json
        scenario_type = data.get('type')
        scenario_name = data.get('name', f"scenario_{datetime.now().strftime('%H%M%S')}")

        # Use cached data or load fresh
        df_original = current_data.get('df')
        if df_original is None:
            file_path = current_data.get('file_path')
            if file_path and os.path.exists(file_path):
                df_original = load_and_prepare_data(file_path)
            else:
                df_original = load_and_prepare_data()
            current_data['df'] = df_original

        # Senaryo tipine göre işle
        if scenario_type == 'payment_reduction_year':
            df_scenario = create_payment_reduction_year(df_original, data)
            description = f"Kaza Yılı Bazlı: {data.get('years')} yılları, %{data.get('reduction_pct')} azaltma"
        elif scenario_type == 'payment_reduction_file':
            df_scenario = create_payment_reduction_file(df_original, data)
            description = f"Dosya Bazlı: {len(data.get('claim_numbers', []))} dosya ödenmedi"
        elif scenario_type == 'reserve_payment_year':
            df_scenario = create_reserve_payment_year(df_original, data)
            description = f"Muallak Kaza Yılı: {data.get('years')} yılları, %{data.get('payment_pct')} ödendi"
        elif scenario_type == 'reserve_payment_file':
            df_scenario = create_reserve_payment_file(df_original, data)
            description = f"Muallak Dosya: {len(data.get('claim_numbers', []))} dosyanın muallağı ödendi"
        else:
            return jsonify({
                'success': False,
                'error': 'Geçersiz senaryo tipi'
            }), 400

        # Cashflow pattern hesapla
        df_scenario_formatted = convert_to_cashflow_format(df_scenario)
        scenario_data = calculate_cashflow_pattern(
            df_scenario_formatted,
            f'scenario_{scenario_name}',
            OUTPUT_DIR
        )

        # Session'a ekle
        scenarios = session.get('scenarios', [])
        scenarios.append({
            'name': scenario_name,
            'type': scenario_type,
            'description': description,
            'params': data,
            'created_at': datetime.now().isoformat(),
            'file': f'scenario_{scenario_name}.xlsx'
        })
        session['scenarios'] = scenarios

        return jsonify({
            'success': True,
            'message': f'Senaryo "{scenario_name}" başarıyla oluşturuldu',
            'scenario': {
                'name': scenario_name,
                'type': scenario_type,
                'description': description,
                'file': f'scenario_{scenario_name}.xlsx'
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/comparison/create', methods=['POST'])
def create_comparison():
    """Karşılaştırma Excel'i oluştur"""
    try:
        scenarios = session.get('scenarios', [])

        if not scenarios:
            return jsonify({
                'success': False,
                'error': 'Karşılaştırma için en az bir senaryo gerekli'
            }), 400

        # Use cached data or load fresh
        df_original = current_data.get('df')
        if df_original is None:
            file_path = current_data.get('file_path')
            if file_path and os.path.exists(file_path):
                df_original = load_and_prepare_data(file_path)
            else:
                df_original = load_and_prepare_data()
            current_data['df'] = df_original
        df_base = convert_to_cashflow_format(df_original)
        base_data = calculate_cashflow_pattern(df_base, 'base_cashflow', OUTPUT_DIR)

        # Scenario dataları yükle
        scenarios_data = {}
        for scenario in scenarios:
            df_scenario_original = df_original.copy()

            # Senaryoyu yeniden oluştur
            scenario_type = scenario['type']
            data = scenario.get('params', {})

            if scenario_type == 'payment_reduction_year':
                df_scenario = create_payment_reduction_year(df_scenario_original, data)
            elif scenario_type == 'payment_reduction_file':
                df_scenario = create_payment_reduction_file(df_scenario_original, data)
            elif scenario_type == 'reserve_payment_year':
                df_scenario = create_reserve_payment_year(df_scenario_original, data)
            elif scenario_type == 'reserve_payment_file':
                df_scenario = create_reserve_payment_file(df_scenario_original, data)

            df_scenario_formatted = convert_to_cashflow_format(df_scenario)
            scenario_data = calculate_cashflow_pattern(
                df_scenario_formatted,
                f'scenario_{scenario["name"]}',
                OUTPUT_DIR
            )
            scenarios_data[scenario['name']] = scenario_data

        # Karşılaştırma Excel'i oluştur
        create_comparison_excel(base_data, scenarios_data, OUTPUT_DIR)

        return jsonify({
            'success': True,
            'message': 'Karşılaştırma Excel\'i başarıyla oluşturuldu',
            'file': 'comparison_all.xlsx'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/download/<filename>')
def download_file(filename):
    """Excel dosyasını indir"""
    try:
        file_path = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'Dosya bulunamadı'
            }), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/scenario/delete/<scenario_name>', methods=['DELETE'])
def delete_scenario(scenario_name):
    """Senaryoyu sil"""
    try:
        scenarios = session.get('scenarios', [])
        scenarios = [s for s in scenarios if s['name'] != scenario_name]
        session['scenarios'] = scenarios

        # Dosyayı sil
        file_path = os.path.join(OUTPUT_DIR, f'scenario_{scenario_name}.xlsx')
        if os.path.exists(file_path):
            os.remove(file_path)

        return jsonify({
            'success': True,
            'message': f'Senaryo "{scenario_name}" silindi'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Helper functions for scenario creation
def create_payment_reduction_year(df_original, data):
    """Kaza yılı bazlı ödeme azaltma"""
    years = data.get('years', [])
    reduction_pct = data.get('reduction_pct', 0)

    df_scenario = df_original.copy()
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['ORIGIN_YEAR'].isin(years)) &
        (df_scenario['MB_FINAL'] == 'Bodily')
    )

    df_scenario.loc[condition, 'PAID_TL'] = (
        df_scenario.loc[condition, 'PAID_TL'] * (1 - reduction_pct / 100)
    )

    return df_scenario


def create_payment_reduction_file(df_original, data):
    """Dosya bazlı ödeme azaltma"""
    claim_numbers = data.get('claim_numbers', [])

    df_scenario = df_original.copy()
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['CLAIM_NO'].isin(claim_numbers))
    )

    df_scenario.loc[condition, 'PAID_TL'] = 0

    return df_scenario


def create_reserve_payment_year(df_original, data):
    """Kaza yılı bazlı muallak ödeme"""
    years = data.get('years', [])
    payment_pct = data.get('payment_pct', 0)

    df_scenario = df_original.copy()
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['ORIGIN_YEAR'].isin(years)) &
        (df_scenario['MB_FINAL'] == 'Bodily')
    )

    df_scenario.loc[condition, 'PAID_TL'] = (
        df_scenario.loc[condition, 'PAID_TL'] +
        df_scenario.loc[condition, 'OS_TL'] * (payment_pct / 100)
    )

    df_scenario.loc[condition, 'OS_TL'] = (
        df_scenario.loc[condition, 'OS_TL'] * (1 - payment_pct / 100)
    )

    return df_scenario


def create_reserve_payment_file(df_original, data):
    """Dosya bazlı muallak ödeme"""
    claim_numbers = data.get('claim_numbers', [])

    df_scenario = df_original.copy()
    condition = (
        (df_scenario['YEARMONTH'] == 202409) &
        (df_scenario['CLAIM_NO'].isin(claim_numbers))
    )

    df_scenario.loc[condition, 'PAID_TL'] = (
        df_scenario.loc[condition, 'PAID_TL'] +
        df_scenario.loc[condition, 'OS_TL']
    )

    df_scenario.loc[condition, 'OS_TL'] = 0

    return df_scenario


# =====================================================
# Excel Preview API Endpoints
# =====================================================

@app.route('/api/preview/base')
def preview_base():
    """Base cashflow Excel'ini önizle"""
    try:
        sheet = request.args.get('sheet', 'cumulative')
        file_path = os.path.join(OUTPUT_DIR, 'base_cashflow.xlsx')

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'Base cashflow dosyası bulunamadı. Önce veriyi yükleyin.'
            }), 404

        # Sheet name mapping - Türkçe sheet isimleri
        sheet_names = {
            'cumulative': 'kümül data',
            'pattern': 'cashflow pattern',
            'triangle': 'üçgen',
            'devfactors': 'dev factorleri',
            'monthly': '180 aylık pattern'
        }

        sheet_name = sheet_names.get(sheet, 'kümül data')

        # Excel dosyasını oku - sheet yoksa alternatif dene
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        except ValueError:
            # Sheet bulunamadı, mevcut sheet'leri kontrol et
            xl = pd.ExcelFile(file_path)
            available_sheets = xl.sheet_names
            if available_sheets:
                df = pd.read_excel(file_path, sheet_name=available_sheets[0])
            else:
                return jsonify({'success': False, 'error': f'Sheet bulunamadı: {sheet_name}'}), 404

        # DataFrame'i JSON formatına çevir
        columns = df.columns.tolist()
        rows = df.values.tolist()

        # Sayıları formatla
        formatted_rows = []
        for row in rows:
            formatted_row = []
            for val in row:
                if isinstance(val, (int, float)) and not pd.isna(val):
                    if abs(val) >= 1000:
                        formatted_row.append(f"{val:,.2f}")
                    else:
                        formatted_row.append(f"{val:.4f}" if val < 1 and val > 0 else f"{val:.2f}")
                elif pd.isna(val):
                    formatted_row.append('')
                else:
                    formatted_row.append(str(val))
            formatted_rows.append(formatted_row)

        return jsonify({
            'success': True,
            'sheet': sheet_name,
            'columns': columns,
            'rows': formatted_rows,
            'total_rows': len(rows)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preview/scenario')
def preview_scenario():
    """Senaryo Excel'ini önizle"""
    try:
        file = request.args.get('file', '')
        sheet = request.args.get('sheet', 'cumulative')

        if not file:
            return jsonify({
                'success': False,
                'error': 'Dosya adı gerekli'
            }), 400

        file_path = os.path.join(OUTPUT_DIR, file)

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': f'Senaryo dosyası bulunamadı: {file}'
            }), 404

        # Sheet name mapping - Türkçe sheet isimleri
        sheet_names = {
            'cumulative': 'kümül data',
            'pattern': 'cashflow pattern',
            'triangle': 'üçgen',
            'devfactors': 'dev factorleri',
            'monthly': '180 aylık pattern'
        }

        sheet_name = sheet_names.get(sheet, 'kümül data')

        # Excel dosyasını oku - sheet yoksa alternatif dene
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        except ValueError:
            # Sheet bulunamadı, mevcut sheet'leri kontrol et
            xl = pd.ExcelFile(file_path)
            available_sheets = xl.sheet_names
            if available_sheets:
                df = pd.read_excel(file_path, sheet_name=available_sheets[0])
            else:
                return jsonify({'success': False, 'error': f'Sheet bulunamadı: {sheet_name}'}), 404

        # DataFrame'i JSON formatına çevir
        columns = df.columns.tolist()
        rows = df.values.tolist()

        # Sayıları formatla
        formatted_rows = []
        for row in rows:
            formatted_row = []
            for val in row:
                if isinstance(val, (int, float)) and not pd.isna(val):
                    if abs(val) >= 1000:
                        formatted_row.append(f"{val:,.2f}")
                    else:
                        formatted_row.append(f"{val:.4f}" if val < 1 and val > 0 else f"{val:.2f}")
                elif pd.isna(val):
                    formatted_row.append('')
                else:
                    formatted_row.append(str(val))
            formatted_rows.append(formatted_row)

        return jsonify({
            'success': True,
            'file': file,
            'sheet': sheet_name,
            'columns': columns,
            'rows': formatted_rows,
            'total_rows': len(rows)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preview/comparison')
def preview_comparison():
    """Karşılaştırma Excel'ini önizle"""
    try:
        sheet = request.args.get('sheet', 'summary')
        file_path = os.path.join(OUTPUT_DIR, 'comparison_all.xlsx')

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'Karşılaştırma dosyası bulunamadı. Önce karşılaştırma oluşturun.'
            }), 404

        # Sheet listesini al
        xl = pd.ExcelFile(file_path)
        available_sheets = xl.sheet_names

        # Sheet name mapping
        sheet_names = {
            'summary': 'Summary',
            'cumulative': 'Cumulative Comparison',
            'pattern': 'Pattern Comparison'
        }

        sheet_name = sheet_names.get(sheet, available_sheets[0] if available_sheets else 'Summary')

        # Sheet mevcut değilse ilk sheet'i kullan
        if sheet_name not in available_sheets:
            sheet_name = available_sheets[0] if available_sheets else None
            if not sheet_name:
                return jsonify({
                    'success': False,
                    'error': 'Excel dosyasında sheet bulunamadı'
                }), 404

        # Excel dosyasını oku
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        # DataFrame'i JSON formatına çevir
        columns = df.columns.tolist()
        rows = df.values.tolist()

        # Sayıları formatla
        formatted_rows = []
        for row in rows:
            formatted_row = []
            for val in row:
                if isinstance(val, (int, float)) and not pd.isna(val):
                    if abs(val) >= 1000:
                        formatted_row.append(f"{val:,.2f}")
                    else:
                        formatted_row.append(f"{val:.4f}" if val < 1 and val > 0 else f"{val:.2f}")
                elif pd.isna(val):
                    formatted_row.append('')
                else:
                    formatted_row.append(str(val))
            formatted_rows.append(formatted_row)

        return jsonify({
            'success': True,
            'sheet': sheet_name,
            'available_sheets': available_sheets,
            'columns': columns,
            'rows': formatted_rows,
            'total_rows': len(rows)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scenario/analysis/<scenario_name>')
def scenario_analysis(scenario_name):
    """Senaryo analizi - base ile karşılaştırma"""
    try:
        # Base pattern dosyasını oku
        base_file = os.path.join(OUTPUT_DIR, 'base_cashflow.xlsx')
        scenario_file = os.path.join(OUTPUT_DIR, f'scenario_{scenario_name}.xlsx')

        if not os.path.exists(base_file):
            return jsonify({
                'success': False,
                'error': 'Base cashflow dosyası bulunamadı'
            }), 404

        if not os.path.exists(scenario_file):
            return jsonify({
                'success': False,
                'error': f'Senaryo dosyası bulunamadı: {scenario_name}'
            }), 404

        # Pattern sheet'lerini oku - Türkçe isimler
        base_pattern = pd.read_excel(base_file, sheet_name='cashflow pattern')
        scenario_pattern = pd.read_excel(scenario_file, sheet_name='cashflow pattern')

        # Cumulative sheet'lerini oku - Türkçe isimler
        base_cumulative = pd.read_excel(base_file, sheet_name='kümül data')
        scenario_cumulative = pd.read_excel(scenario_file, sheet_name='kümül data')

        # Cashflow pattern: Her yıl için period bazlı ağırlıklar var
        # Her yılın ilk satırının (Period=1) ağırlığını al
        base_weights_by_period = base_pattern.groupby('Period')['Normalize Ağırlık'].mean().tolist()
        scenario_weights_by_period = scenario_pattern.groupby('Period')['Normalize Ağırlık'].mean().tolist()

        # Development periods
        dev_periods = list(range(1, len(base_weights_by_period) + 1))

        # Toplam paid karşılaştırması - kümül data'daki PAID_TL toplamı
        if 'PAID_TL' in base_cumulative.columns:
            base_total = float(base_cumulative['PAID_TL'].sum())
            scenario_total = float(scenario_cumulative['PAID_TL'].sum())
        else:
            # Alternatif: son sütunu al
            base_total = float(base_cumulative.iloc[:, -1].sum())
            scenario_total = float(scenario_cumulative.iloc[:, -1].sum())

        # Fark hesapla
        total_diff = scenario_total - base_total
        total_diff_pct = (total_diff / base_total * 100) if base_total != 0 else 0

        return jsonify({
            'success': True,
            'scenario_name': scenario_name,
            'pattern': {
                'dev_periods': dev_periods,
                'base_weights': [float(w) if pd.notna(w) else 0 for w in base_weights_by_period],
                'scenario_weights': [float(w) if pd.notna(w) else 0 for w in scenario_weights_by_period]
            },
            'summary': {
                'base_total': base_total,
                'scenario_total': scenario_total,
                'difference': total_diff,
                'difference_pct': total_diff_pct
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/summary/by-year')
def summary_by_year():
    """Hasar yılı bazlı özet veriler"""
    try:
        df = current_data.get('df')
        if df is None:
            return jsonify({
                'success': False,
                'error': 'Veri yüklenmemiş'
            }), 400

        # 202409 verileri
        df_202409 = df[df['YEARMONTH'] == 202409].copy()

        # Yıl bazlı gruplama
        summary = df_202409.groupby('ORIGIN_YEAR').agg({
            'PAID_TL': 'sum',
            'OS_TL': 'sum',
            'CLAIM_NO': 'nunique'
        }).reset_index()

        summary.columns = ['year', 'paid', 'reserve', 'claims']
        summary['incurred'] = summary['paid'] + summary['reserve']
        summary = summary.sort_values('year')

        # JSON için formatla
        records = summary.to_dict('records')
        for r in records:
            r['year'] = int(r['year'])
            r['paid'] = float(r['paid'])
            r['reserve'] = float(r['reserve'])
            r['incurred'] = float(r['incurred'])
            r['claims'] = int(r['claims'])

        return jsonify({
            'success': True,
            'data': records
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/years')
def get_years():
    """Mevcut kaza yıllarını döndür"""
    try:
        df = current_data.get('df')
        if df is None:
            return jsonify({'success': False, 'error': 'Veri yüklenmemiş'}), 400

        years = sorted(df['ORIGIN_YEAR'].unique().tolist())
        return jsonify({
            'success': True,
            'years': [int(y) for y in years]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cashflow/quarterly')
def quarterly_cashflow():
    """Çeyreklik cashflow karşılaştırması - Seçilen yılların ortalaması"""
    try:
        base_file = os.path.join(OUTPUT_DIR, 'base_cashflow.xlsx')
        if not os.path.exists(base_file):
            return jsonify({
                'success': False,
                'error': 'Base cashflow dosyası bulunamadı'
            }), 404

        # Kaza yılı filtresi
        years_param = request.args.get('years', '')
        filter_years = [int(y) for y in years_param.split(',') if y.strip()] if years_param else None

        # Base cashflow pattern oku
        base_pattern = pd.read_excel(base_file, sheet_name='cashflow pattern')

        # Yıl filtresi varsa uygula
        if filter_years:
            base_pattern = base_pattern[base_pattern['Kaza Yılı'].isin(filter_years)]

        # Period listesi (1-60 arası çeyrekler)
        all_periods = sorted(base_pattern['Period'].unique())
        quarters = [f"Q{int(p)}" for p in all_periods]

        # Seçilen yılların ortalamasını hesapla (Period bazında)
        base_avg = base_pattern.groupby('Period')['Normalize Ağırlık'].mean()
        base_weights = [float(base_avg.get(p, 0)) for p in all_periods]

        # Senaryoların ortalamasını hesapla
        scenarios = session.get('scenarios', [])
        scenario_weights = {}

        for scenario in scenarios:
            scenario_file = os.path.join(OUTPUT_DIR, f'scenario_{scenario["name"]}.xlsx')
            if os.path.exists(scenario_file):
                try:
                    scenario_pattern = pd.read_excel(scenario_file, sheet_name='cashflow pattern')

                    # Yıl filtresi varsa uygula
                    if filter_years:
                        scenario_pattern = scenario_pattern[scenario_pattern['Kaza Yılı'].isin(filter_years)]

                    # Seçilen yılların ortalaması
                    scenario_avg = scenario_pattern.groupby('Period')['Normalize Ağırlık'].mean()
                    weights = [float(scenario_avg.get(p, 0)) for p in all_periods]
                    scenario_weights[scenario['name']] = weights
                except Exception as e:
                    print(f"Error reading scenario {scenario['name']}: {e}")

        return jsonify({
            'success': True,
            'quarters': quarters,
            'base': base_weights,
            'scenarios': scenario_weights
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/files/list')
def list_output_files():
    """Output klasöründeki tüm Excel dosyalarını listele"""
    try:
        files = []
        if os.path.exists(OUTPUT_DIR):
            for filename in os.listdir(OUTPUT_DIR):
                if filename.endswith('.xlsx'):
                    file_path = os.path.join(OUTPUT_DIR, filename)
                    stat = os.stat(file_path)
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'size_formatted': f"{stat.st_size / 1024:.1f} KB",
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })

        # Sort by modification time, newest first
        files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================
# Oracle Connection API Endpoints
# =====================================================

@app.route('/api/oracle/connect', methods=['POST'])
def oracle_connect():
    """Oracle veritabanına bağlan"""
    try:
        data = request.json
        host = data.get('host')
        port = int(data.get('port', 1521))
        service = data.get('service')
        username = data.get('username')
        password = data.get('password')

        if not all([host, service, username, password]):
            return jsonify({
                'success': False,
                'error': 'Tüm bağlantı bilgileri gerekli'
            }), 400

        oracle_db.connect(host, port, service, username, password)

        # Set connector for analysis engine
        analysis_engine.set_connector(oracle_db)

        # Save connection info to session (not password)
        session['oracle_connected'] = True
        session['oracle_config'] = {
            'host': host,
            'port': port,
            'service': service,
            'username': username
        }

        return jsonify({
            'success': True,
            'message': 'Oracle bağlantısı başarılı',
            'config': session['oracle_config']
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/test')
def oracle_test():
    """Oracle bağlantısını test et"""
    try:
        result = oracle_db.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/disconnect', methods=['POST'])
def oracle_disconnect():
    """Oracle bağlantısını kapat"""
    try:
        oracle_db.close()
        session.pop('oracle_connected', None)
        session.pop('oracle_config', None)
        return jsonify({'success': True, 'message': 'Bağlantı kapatıldı'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/status')
def oracle_status():
    """Oracle bağlantı durumu"""
    return jsonify({
        'connected': oracle_db.is_connected(),
        'config': session.get('oracle_config', {})
    })


@app.route('/api/oracle/tables')
def oracle_tables():
    """Oracle tablolarını listele"""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        schema = request.args.get('schema', None)
        tables = oracle_db.get_tables(schema)
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/fetch-data', methods=['POST'])
def oracle_fetch_data():
    """Oracle'dan veri çek"""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        data = request.json
        table_name = data.get('table')
        query = data.get('query')

        if query:
            df = oracle_db.execute_query(query)
        elif table_name:
            df = oracle_db.execute_query(f"SELECT * FROM {table_name}")
        else:
            return jsonify({'success': False, 'error': 'Tablo adı veya sorgu gerekli'}), 400

        # Store in memory
        current_data['df'] = df
        current_data['file_path'] = 'oracle_query'

        return jsonify({
            'success': True,
            'message': f'{len(df)} satır veri çekildi',
            'rows': len(df),
            'columns': df.columns.tolist()
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def _run_oracle_load_job(job_id, query):
    """Arka planda Oracle veri yükleme ve base cashflow hesaplama (thread'de çalışır)."""
    try:
        df_original = oracle_db.execute_query(query)

        required_cols = ['CLAIM_NO', 'ORIGIN_YEAR', 'YEARMONTH', 'PAID_TL', 'OS_TL']
        missing_cols = [col for col in required_cols if col not in df_original.columns]
        if missing_cols:
            oracle_load_jobs[job_id] = {
                'status': 'error',
                'error': f'Eksik kolonlar: {", ".join(missing_cols)}. Gerekli: {", ".join(required_cols)}'
            }
            return

        current_data['df'] = df_original
        current_data['file_path'] = 'oracle_query'

        df_base = convert_to_cashflow_format(df_original)
        calculate_cashflow_pattern(df_base, 'base_cashflow', OUTPUT_DIR)

        total_rows = len(df_original)
        unique_claims = df_original['CLAIM_NO'].nunique()
        years = sorted(df_original['ORIGIN_YEAR'].unique().tolist())
        max_yearmonth = df_original['YEARMONTH'].max()
        df_latest = df_original[df_original['YEARMONTH'] == max_yearmonth]
        total_paid = df_latest['PAID_TL'].sum()
        total_os = df_latest['OS_TL'].sum()

        oracle_load_jobs[job_id] = {
            'status': 'done',
            'result': {
                'success': True,
                'message': f'Oracle\'dan {len(df_original)} satır veri yüklendi ve base cashflow hesaplandı',
                'stats': {
                    'total_rows': total_rows,
                    'unique_claims': unique_claims,
                    'years': [int(y) for y in years],
                    'latest_yearmonth': int(max_yearmonth),
                    'total_paid': float(total_paid),
                    'total_os': float(total_os),
                    'base_file': 'base_cashflow.xlsx'
                }
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        oracle_load_jobs[job_id] = {'status': 'error', 'error': str(e)}


@app.route('/api/oracle/load-and-calculate', methods=['POST'])
def oracle_load_and_calculate():
    """Oracle yükleme işini başlat; hesaplama arka planda yapılır, sonuç polling ile alınır."""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        data = request.json or {}
        query = (data.get('query') or '').strip()

        if not query:
            return jsonify({'success': False, 'error': 'SQL sorgusu gerekli'}), 400

        job_id = str(uuid.uuid4())
        oracle_load_jobs[job_id] = {'status': 'running'}

        thread = threading.Thread(
            target=_run_oracle_load_job,
            args=(job_id, query),
            daemon=True
        )
        thread.start()

        return jsonify({'success': True, 'job_id': job_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/load-job/<job_id>', methods=['GET'])
def oracle_load_job_status(job_id):
    """Arka plan Oracle yükleme işinin durumunu döndür; done ise session güncellenir."""
    try:
        job = oracle_load_jobs.get(job_id)
        if not job:
            return jsonify({'success': False, 'error': 'İş bulunamadı'}), 404

        status = job.get('status', 'running')
        if status == 'done':
            session.clear()
            session['data_loaded'] = True
            session['scenarios'] = []
            return jsonify({'success': True, 'status': 'done', 'result': job['result']})
        if status == 'error':
            return jsonify({'success': False, 'status': 'error', 'error': job.get('error', 'Bilinmeyen hata')})
        return jsonify({'success': True, 'status': 'running'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/oracle/write-cashflows', methods=['POST'])
def oracle_write_cashflows():
    """180 aylık cashflow pattern'ları Oracle'a yaz. İsimler: base_YYMM, senaryo_YYMM."""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        data = request.json or {}
        # run_id = YYMM (örn. 2410); pattern adı = base_2410, Senaryo1_2410
        run_id = data.get('run_id') or datetime.now().strftime('%y%m')
        scenarios_to_write = data.get('scenarios', ['Base'])

        base_file = os.path.join(OUTPUT_DIR, 'base_cashflow.xlsx')
        if not os.path.exists(base_file):
            return jsonify({'success': False, 'error': 'Base cashflow dosyası bulunamadı'}), 404

        written = {}
        pattern_names = []

        def read_180_weights_by_year(excel_path):
            """Excel '180 aylık pattern' sayfasını oku; Kaza Yılı bazında (accident_year, months, weights) listesi döner."""
            try:
                df = pd.read_excel(excel_path, sheet_name='180 aylık pattern')
            except ValueError:
                return []
            if df.empty:
                return []
            year_col = None
            period_col = None
            weight_col = None
            for col in df.columns:
                c = str(col).lower()
                if 'kaza' in c or 'year' in c or col == 'ORIGIN_YEAR':
                    year_col = col
                if 'ay' in c or 'period' in c or col == 'Period':
                    period_col = col
                if 'ağırlık' in c or 'weight' in c or 'rate' in c:
                    weight_col = col
            if period_col is None:
                period_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            if weight_col is None:
                for col in df.columns:
                    if df[col].dtype in ['float64', 'int64'] and col != year_col and col != period_col:
                        weight_col = col
                        break
            if weight_col is None:
                return []
            if year_col is None:
                years = [None]
            else:
                years = sorted(df[year_col].dropna().unique().tolist())
                if not years:
                    years = [None]

            result = []
            sort_col = period_col if period_col in df.columns else (df.columns[0] if len(df.columns) else None)
            for year in years:
                if year is not None:
                    sub = df[df[year_col] == year].copy()
                else:
                    sub = df.copy()
                if sort_col and sort_col in sub.columns:
                    sub = sub.sort_values(sort_col)
                months = list(range(1, len(sub) + 1))
                weights = [round(float(sub[weight_col].iloc[i]) if pd.notna(sub[weight_col].iloc[i]) else 0.0, 10)
                           for i in range(len(sub))]
                if len(months) > 0:
                    result.append((int(year) if year is not None else None, months, weights))
            return result

        # Base: kaza yılı bazlı yaz
        if 'Base' in scenarios_to_write:
            by_year = read_180_weights_by_year(base_file)
            if by_year:
                pattern_name = f'base_{run_id}'
                oracle_db.delete_cashflow_patterns_for_scenario(run_id, pattern_name)
                total_rows = 0
                for accident_year, months, weights in by_year:
                    rows = oracle_db.write_cashflow_patterns(
                        run_id, pattern_name, months, weights,
                        accident_year=accident_year
                    )
                    total_rows += rows
                written['Base'] = total_rows
                pattern_names.append(pattern_name)

        # Senaryolar: kaza yılı bazlı yaz
        session_scenarios = session.get('scenarios', [])
        for scenario in session_scenarios:
            if scenario['name'] in scenarios_to_write:
                scenario_file = os.path.join(OUTPUT_DIR, f"scenario_{scenario['name']}.xlsx")
                if os.path.exists(scenario_file):
                    by_year = read_180_weights_by_year(scenario_file)
                    if by_year:
                        pattern_name = f"{scenario['name']}_{run_id}"
                        oracle_db.delete_cashflow_patterns_for_scenario(run_id, pattern_name)
                        total_rows = 0
                        for accident_year, months, weights in by_year:
                            rows = oracle_db.write_cashflow_patterns(
                                run_id, pattern_name, months, weights,
                                accident_year=accident_year
                            )
                            total_rows += rows
                        written[scenario['name']] = total_rows
                        pattern_names.append(pattern_name)

        session['oracle_run_id'] = run_id
        session['oracle_pattern_names'] = pattern_names

        return jsonify({
            'success': True,
            'run_id': run_id,
            'pattern_names': pattern_names,
            'written': written,
            'message': f'{sum(written.values())} satır yazıldı ({len(written)} pattern)'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================
# SQL Scripts API Endpoints
# =====================================================

@app.route('/api/scripts', methods=['GET'])
def get_scripts():
    """Tüm SQL scriptlerini listele"""
    scripts = script_manager.get_all()
    return jsonify({'success': True, 'scripts': scripts})


@app.route('/api/scripts', methods=['POST'])
def add_script():
    """Yeni SQL script ekle"""
    try:
        data = request.json
        script = script_manager.add(data)
        return jsonify({'success': True, 'script': script})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scripts/<script_id>', methods=['GET'])
def get_script(script_id):
    """Script detayını getir"""
    script = script_manager.get_by_id(script_id)
    if script:
        return jsonify({'success': True, 'script': script})
    return jsonify({'success': False, 'error': 'Script bulunamadı'}), 404


@app.route('/api/scripts/<script_id>', methods=['PUT'])
def update_script(script_id):
    """Script güncelle"""
    try:
        data = request.json
        script = script_manager.update(script_id, data)
        if script:
            return jsonify({'success': True, 'script': script})
        return jsonify({'success': False, 'error': 'Script bulunamadı'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scripts/<script_id>', methods=['DELETE'])
def delete_script(script_id):
    """Script sil"""
    try:
        if script_manager.delete(script_id):
            return jsonify({'success': True, 'message': 'Script silindi'})
        return jsonify({'success': False, 'error': 'Script bulunamadı'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scripts/<script_id>/test', methods=['POST'])
def test_script(script_id):
    """Script'i test et"""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        data = request.json
        params = data.get('params', {})

        script = script_manager.get_by_id(script_id)
        if not script:
            return jsonify({'success': False, 'error': 'Script bulunamadı'}), 404

        result = analysis_engine.execute_script_with_params(script, params)
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scripts/reorder', methods=['POST'])
def reorder_scripts():
    """Script sırasını değiştir"""
    try:
        data = request.json
        script_ids = data.get('script_ids', [])

        if not script_ids:
            return jsonify({'success': False, 'error': 'Script ID listesi gerekli'}), 400

        script_manager.reorder(script_ids)
        return jsonify({
            'success': True,
            'message': 'Script sırası güncellendi'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =====================================================
# Analysis API Endpoints
# =====================================================

def _do_run_by_patterns(data):
    """Tek script'i her pattern için çalıştır; data dict kullanır."""
    script_id = data.get('script_id')
    run_id = data.get('run_id') or session.get('oracle_run_id')
    pattern_names = data.get('pattern_names') or session.get('oracle_pattern_names') or []
    params = data.get('params', {})
    if not script_id:
        return jsonify({'success': False, 'error': 'Script seçin'}), 400
    if not pattern_names:
        return jsonify({'success': False, 'error': "Önce Oracle'a pattern yazın (Write Cashflows)"}), 400
    if not run_id:
        run_id = datetime.now().strftime('%y%m')
    result = analysis_engine.run_script_by_patterns(
        script_id=script_id,
        run_id=str(run_id),
        pattern_names=pattern_names,
        user_params=params,
        cf_table_name='CF_PATTERNS'
    )
    return jsonify({'success': True, **result})


@app.route('/api/analysis/run-by-patterns', methods=['POST'])
def run_analysis_by_patterns():
    """
    Tek script'i her pattern için çalıştır; &cf_pattern, &run_id, &scenario_name substitute edilir.
    Sonuç: { run_id, pl_values: { base_2410: 50, scenario1_2410: 45 } }
    """
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400
        data = request.json or {}
        script_id = data.get('script_id')
        run_id = data.get('run_id') or session.get('oracle_run_id')
        pattern_names = data.get('pattern_names') or session.get('oracle_pattern_names') or []
        params = data.get('params', {})

        return _do_run_by_patterns(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/run', methods=['POST'])
def run_analysis():
    """
    Tek script + pattern listesi ile run-by-patterns kullanır.
    """
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400
        data = request.json or {}
        script_ids = data.get('scripts', [])
        if not script_ids:
            return jsonify({'success': False, 'error': 'Script seçin'}), 400
        run_id = session.get('oracle_run_id') or datetime.now().strftime('%y%m')
        pattern_names = session.get('oracle_pattern_names') or []
        if len(script_ids) == 1 and pattern_names:
            data['script_id'] = script_ids[0]
            data['run_id'] = run_id
            data['pattern_names'] = pattern_names
            data['params'] = data.get('params', {})
            return _do_run_by_patterns(data)
        if not pattern_names:
            return jsonify({'success': False, 'error': "Önce Oracle'a pattern yazın (Write Cashflows)"}), 400
        return jsonify({'success': False, 'error': 'Tek bir script seçin'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analysis/history')
def analysis_history():
    """Analiz geçmişi"""
    try:
        if not oracle_db.is_connected():
            return jsonify({'success': False, 'error': 'Oracle bağlantısı yok'}), 400

        limit = request.args.get('limit', 100, type=int)
        df = oracle_db.get_analysis_history(limit)

        return jsonify({
            'success': True,
            'history': df.to_dict('records')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("CASHFLOW PATTERN SENARYO ANALİZİ - WEB ARAYÜZÜ")
    print("=" * 80)
    print("\nWeb arayüzü başlatılıyor...")
    print("Tarayıcınızda şu adresi açın: http://localhost:5001")
    print("\nÇıkmak için Ctrl+C tuşlarına basın")
    print("=" * 80)

    app.run(debug=True, host='0.0.0.0', port=5001)
