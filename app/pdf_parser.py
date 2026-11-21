"""Text-PDF question parser, shared by local and Cloudflare-backed deployments."""
import re
from .schemas import ItemCreate

def parse_questions(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blocks = []
    current = None
    for line in lines:
        question = re.match(r'^(?:Q(?:uestion)?\s*)?(\d+)[.)\s:]\s*(.+)$', line, re.I)
        option = re.match(r'^([A-H])[.)\s:]\s*(.+)$', line)
        answer = re.match(r'^(?:Correct\s+)?Answer\s*:\s*([A-H](?:\s*[, &]\s*[A-H])*)\s*$', line, re.I)
        if answer and current:
            current['key'] = re.findall(r'[A-H]', answer.group(1).upper())
        elif question:
            current = {'number': question.group(1), 'stem': question.group(2), 'options': [], 'key': []}
            blocks.append(current)
        elif option and current:
            current['options'].append({'id': option.group(1), 'text': option.group(2)})
        elif current:
            if current['key']:
                raise ValueError('Unexpected text after an answer. Use the PDF template format.')
            if current['options']:
                current['options'][-1]['text'] += ' ' + line
            else:
                current['stem'] += ' ' + line
    if not blocks:
        raise ValueError('No numbered questions found. Scanned PDFs need OCR first. Use a text PDF with numbered questions, A. options and Answer: A.')
    if len(blocks) > 200:
        raise ValueError('Import at most 200 questions per bank.')
    items = []
    for block in blocks:
        if not block['key'] or not set(block['key']) <= {o['id'] for o in block['options']}:
            raise ValueError(f"Question {block['number']} needs a valid Answer: A line. No answers were guessed.")
        item = ItemCreate(item_id='q'+block['number'], skill_id='imported', stem=block['stem'],
                          kind='multiple' if len(block['key']) > 1 else 'single',
                          options=[{**o, 'is_correct': o['id'] in block['key']} for o in block['options']])
        items.append(item.model_dump())
    if len({i['item_id'] for i in items}) != len(items):
        raise ValueError('Question numbers must be unique.')
    return items


