import json
from pathlib import Path
from collections import Counter

JSONL_PATH = Path(r'C:\Users\parkg\OneDrive\바탕 화면\preprocess/rag_health_supplements_preprocessed.jsonl')
# 다른 폴더에서 실행하는 경우 절대경로 수정 요망

REQUIRED_TOP_FIELDS = {'id', 'text', 'metadata'}
REQUIRED_META_FIELDS = {
    'food_code', 'product_name', 'representative_ingredient', 'source_name',
    'serving_size', 'daily_intake_frequency', 'chunk_type', 'nutrients'
}


def load_jsonl(path):
    rows = []
    with path.open(encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f'{line_no}번째 줄 JSON 파싱 실패: {e}')
    return rows


def validate(rows):
    errors = []
    ids = []
    chunk_types = Counter()
    source_names = Counter()
    representative_ingredients = Counter()
    nutrient_count_distribution = Counter()

    for i, row in enumerate(rows, start=1):
        missing_top = REQUIRED_TOP_FIELDS - set(row.keys())
        if missing_top:
            errors.append(f'{i}번째 row 상위 필드 누락: {missing_top}')
            continue

        ids.append(row['id'])

        if not isinstance(row['text'], str) or len(row['text'].strip()) < 10:
            errors.append(f'{i}번째 row text가 너무 짧거나 문자열이 아님')

        meta = row['metadata']
        missing_meta = REQUIRED_META_FIELDS - set(meta.keys())
        if missing_meta:
            errors.append(f'{i}번째 row metadata 필드 누락: {missing_meta}')

        if not meta.get('product_name'):
            errors.append(f'{i}번째 row product_name 비어 있음')
        if not meta.get('source_name'):
            errors.append(f'{i}번째 row source_name 비어 있음')
        if not isinstance(meta.get('nutrients'), list):
            errors.append(f'{i}번째 row nutrients가 list가 아님')
        else:
            nutrient_count_distribution[len(meta['nutrients'])] += 1

        chunk_types[meta.get('chunk_type', '')] += 1
        source_names[meta.get('source_name', '')] += 1
        representative_ingredients[meta.get('representative_ingredient', '')] += 1

    duplicate_ids = [item for item, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append(f'중복 ID 존재: {duplicate_ids[:10]}')

    return {
        'row_count': len(rows),
        'unique_id_count': len(set(ids)),
        'error_count': len(errors),
        'errors_sample': errors[:10],
        'chunk_types': chunk_types.most_common(10),
        'top_sources': source_names.most_common(10),
        'top_representative_ingredients': representative_ingredients.most_common(15),
        'nutrient_count_distribution': nutrient_count_distribution.most_common(20),
    }


if __name__ == '__main__':
    rows = load_jsonl(JSONL_PATH)
    result = validate(rows)

    print('=== 전처리 검증 결과 ===')
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print('\n=== 샘플 2건 ===')
    for row in rows[:2]:
        print(json.dumps(row, ensure_ascii=False, indent=2)[:1500])
        print('-' * 80)
