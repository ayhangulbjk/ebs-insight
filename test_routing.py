#!/usr/bin/env python
"""Test script for intent classifier and router"""

from src.controls.loader import load_catalog
from src.intent.classifier import IntentClassifier
from src.intent.router import ScoreBasedRouter

# Load catalog
catalog = load_catalog('knowledge/controls')
print(f'✓ Catalog loaded: {len(catalog.controls)} controls')

# Initialize classifier
classifier = IntentClassifier(catalog)
print(f'✓ IntentClassifier initialized')

# Initialize router
router = ScoreBasedRouter(catalog)
print(f'✓ ScoreBasedRouter initialized')

# Test cases
test_prompts = [
    'concurrent manager health check',
    'concurrent manager sağlık durumu nedir?',
    'invalid objects var mı?',
    'merhaba nasılsın?',
    'workflow queue status',
    'adop patch application',
    'aktif kullanıcılar',
]

print(f'\n--- Testing Intent Classification ---')
for prompt in test_prompts:
    result = classifier.classify(prompt)
    print(f'\nPrompt: "{prompt}"')
    print(f'  Intent: {result.intent}')
    print(f'  Confidence: {result.confidence:.2%}')
    print(f'  Scores: EBS={result.all_scores["ebs_control"]:.2%}, Chit-chat={result.all_scores["chit_chat"]:.2%}')
    
    # Route if EBS control
    if result.intent == 'ebs_control':
        decision = router.route(prompt, result.intent)
        print(f'  → Selected: {decision.selected_control_id}')
        if decision.candidates:
            print(f'  → Top 3:')
            for c in decision.candidates[:3]:
                print(f'      - {c.control_id}: {c.final_score:.3f} (keyword={c.keyword_match_score:.2f})')
