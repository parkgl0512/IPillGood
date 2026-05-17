import json
import re
import csv
from pathlib import Path
from decimal import Decimal, InvalidOperation

from pathlib import Path

# 다른 폴더에서 실행하는 경우 경로 수정 요망
BASE_DIR = Path(__file__).resolve().parent

RAW_DIR = BASE_DIR / "raw_data"
PROCESSED_DIR = BASE_DIR / "processed_data"

# processed_data 폴더가 없으면 자동 생성
PROCESSED_DIR.mkdir(exist_ok=True)

INPUT_PATH = RAW_DIR / "전국건강기능식품영양성분정보표준데이터.json"
OUTPUT_JSONL = PROCESSED_DIR / "rag_health_supplements_preprocessed.jsonl"
OUTPUT_CSV = PROCESSED_DIR / "rag_health_supplements_preprocessed.csv"
REPORT_JSON = PROCESSED_DIR / "rag_health_supplements_preprocess_report.json"

NUTRIENT_FIELDS = [
    '에너지(kcal)', '수분(g)', '단백질(g)', '지방(g)', '회분(g)', '탄수화물(g)', '당류(g)', '식이섬유(g)',
    '칼슘(mg)', '철(mg)', '인(mg)', '칼륨(mg)', '나트륨(mg)', '비타민 A(μg RAE)', '레티놀(μg)',
    '베타카로틴(μg)', '티아민(mg)', '리보플라빈(mg)', '니아신(mg)', '비타민 C(mg)', '비타민 D(μg)',
    '콜레스테롤(mg)', '포화지방산(g)', '트랜스지방산(g)'
]

# 프로젝트 목적상 검색에 의미 있는 필드만 남깁니다.
META_FIELDS = [
    '식품코드', '식품명', '데이터구분명', '식품대분류명', '대표식품명', '식품중분류명', '영양성분제공단위량',
    '1회분량', '1회분량중량/부피', '1일섭취횟수', '섭취대상', '식품중량/부피', '품목제조신고번호',
    '제조사명', '수입업체명', '유통업체명', '수입여부', '원산지국명', '출처명', '데이터생성일자',
    '데이터기생성일자', '제공기관명'
]

BLANK_VALUES = {'', '해당없음', '없음', 'N/A', 'null', 'None', None}


def clean_text(value):
    if value is None:
        return ''
    value = str(value)
    value = re.sub(r'<[^>]+>', ' ', value)       # HTML 태그 제거
    value = re.sub(r'\s+', ' ', value)          # 연속 공백 제거
    value = value.replace('\u00a0', ' ').strip()
    return value


def normalize_blank(value):
    value = clean_text(value)
    if value in BLANK_VALUES:
        return ''
    return value


def parse_number(value):
    value = normalize_blank(value)
    if value == '':
        return None
    value = value.replace(',', '')
    try:
        return float(Decimal(value))
    except (InvalidOperation, ValueError):
        return None


def split_nutrient_field(field_name):
    # 예: 비타민 D(μg) -> ('비타민 D', 'μg')
    m = re.match(r'^(.*?)\((.*?)\)$', field_name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return field_name.strip(), ''


def build_nutrients(record):
    nutrients = []
    for field in NUTRIENT_FIELDS:
        num = parse_number(record.get(field))
        if num is None:
            continue
        name, unit = split_nutrient_field(field)
        nutrients.append({'name': name, 'amount': num, 'unit': unit})
    return nutrients


def build_text(record, nutrients):
    product = normalize_blank(record.get('식품명'))
    rep = normalize_blank(record.get('대표식품명'))
    mid = normalize_blank(record.get('식품중분류명'))
    unit = normalize_blank(record.get('영양성분제공단위량'))
    serving = normalize_blank(record.get('1회분량'))
    serving_weight = normalize_blank(record.get('1회분량중량/부피'))
    times = normalize_blank(record.get('1일섭취횟수'))
    target = normalize_blank(record.get('섭취대상'))
    maker = normalize_blank(record.get('제조사명'))
    importer = normalize_blank(record.get('수입업체명'))
    origin = normalize_blank(record.get('원산지국명'))
    source = normalize_blank(record.get('출처명')) or normalize_blank(record.get('제공기관명'))

    lines = [f"제품명: {product}"]
    if rep or mid:
        lines.append(f"분류: {rep or mid}")
    if unit:
        lines.append(f"영양성분 제공 단위량: {unit}")
    if serving or serving_weight or times:
        lines.append(f"복용/섭취 기준: 1회분량 {serving or '정보 없음'}, 1회분량중량/부피 {serving_weight or '정보 없음'}, 1일섭취횟수 {times or '정보 없음'}")
    if target:
        lines.append(f"섭취대상: {target}")
    if nutrients:
        nutrient_text = ', '.join([f"{n['name']} {n['amount']:g}{n['unit']}" for n in nutrients])
        lines.append(f"주요 영양성분: {nutrient_text}")
    if maker or importer or origin:
        lines.append(f"제조/수입 정보: 제조사 {maker or '정보 없음'}, 수입업체 {importer or '정보 없음'}, 원산지 {origin or '정보 없음'}")
    if source:
        lines.append(f"출처: {source}")
    return ' '.join(lines)


def preprocess():
    with INPUT_PATH.open(encoding='utf-8') as f:
        raw = json.load(f)

    records = raw.get('records', [])
    processed = []
    seen = set()
    duplicate_count = 0

    for idx, record in enumerate(records, start=1):
        cleaned = {k: normalize_blank(v) for k, v in record.items()}
        nutrients = build_nutrients(cleaned)
        food_code = cleaned.get('식품코드') or f'UNKNOWN-{idx}'
        product_name = cleaned.get('식품명')
        item_report_no = cleaned.get('품목제조신고번호')
        unique_key = (food_code, product_name, item_report_no)
        if unique_key in seen:
            duplicate_count += 1
            continue
        seen.add(unique_key)

        text = build_text(cleaned, nutrients)
        doc = {
            'id': f"hff_{food_code}",
            'text': text,
            'metadata': {
                'food_code': food_code,
                'product_name': product_name,
                'data_type': cleaned.get('데이터구분명'),
                'origin_type': cleaned.get('식품기원명'),
                'major_category': cleaned.get('식품대분류명'),
                'representative_ingredient': cleaned.get('대표식품명'),
                'middle_category': cleaned.get('식품중분류명'),
                'serving_unit': cleaned.get('영양성분제공단위량'),
                'serving_size': cleaned.get('1회분량'),
                'serving_weight_volume': cleaned.get('1회분량중량/부피'),
                'daily_intake_frequency': cleaned.get('1일섭취횟수'),
                'target_user': cleaned.get('섭취대상'),
                'product_weight_volume': cleaned.get('식품중량/부피'),
                'item_report_no': item_report_no,
                'manufacturer': cleaned.get('제조사명'),
                'importer': cleaned.get('수입업체명'),
                'distributor': cleaned.get('유통업체명'),
                'is_imported': cleaned.get('수입여부'),
                'origin_country': cleaned.get('원산지국명'),
                'source_name': cleaned.get('출처명') or cleaned.get('제공기관명'),
                'provider': cleaned.get('제공기관명'),
                'data_created_date': cleaned.get('데이터생성일자'),
                'data_precreated_date': cleaned.get('데이터기생성일자'),
                'source_type': 'official_public_data',
                'language': 'ko',
                'chunk_type': 'product_nutrition_profile',
                'nutrients': nutrients
            }
        }
        processed.append(doc)

    with OUTPUT_JSONL.open('w', encoding='utf-8') as f:
        for doc in processed:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')

    csv_fields = ['id', 'text', 'food_code', 'product_name', 'representative_ingredient', 'middle_category', 'serving_size', 'daily_intake_frequency', 'source_name', 'data_created_date', 'nutrient_count']
    with OUTPUT_CSV.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for doc in processed:
            meta = doc['metadata']
            writer.writerow({
                'id': doc['id'],
                'text': doc['text'],
                'food_code': meta['food_code'],
                'product_name': meta['product_name'],
                'representative_ingredient': meta['representative_ingredient'],
                'middle_category': meta['middle_category'],
                'serving_size': meta['serving_size'],
                'daily_intake_frequency': meta['daily_intake_frequency'],
                'source_name': meta['source_name'],
                'data_created_date': meta['data_created_date'],
                'nutrient_count': len(meta['nutrients'])
            })

    report = {
        'input_file': str(INPUT_PATH),
        'raw_record_count': len(records),
        'processed_document_count': len(processed),
        'duplicate_removed_count': duplicate_count,
        'output_jsonl': str(OUTPUT_JSONL),
        'output_csv': str(OUTPUT_CSV),
        'metadata_core_fields': list(processed[0]['metadata'].keys()) if processed else [],
        'preprocess_steps': [
            'JSON records 로드',
            'HTML 태그/공백/빈값 정제',
            '영양성분 수치 필드 파싱',
            '제품 단위 청크 생성',
            '출처·분류·제조·섭취 기준 메타데이터 구성',
            'RAG 적재용 JSONL 저장',
            '검토용 CSV 저장'
        ]
    }
    with REPORT_JSON.open('w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    preprocess()
