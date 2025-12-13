import re

class PolicyEngine:
    def __init__(self, input_rules=None, output_rules=None):
        self.input_rules = input_rules or []
        self.output_rules = output_rules or []

    def validate_input(self, text):
        for rule in self.input_rules:
            result = rule(text)
            if not result['passed']:
                return result
        return {'passed': True, 'reason': None}

    def moderate_output(self, text):
        for rule in self.output_rules:
            result = rule(text)
            if not result['passed']:
                return result
        return {'passed': True, 'reason': None}

# Input validation rules

def pii_detection_rule(text):
    # Simple regex for email/phone (expand as needed)
    if re.search(r'\b[\w.-]+@[\w.-]+\.\w+\b', text) or re.search(r'\b\d{10}\b', text):
        return {'passed': False, 'reason': 'PII detected'}
    return {'passed': True, 'reason': None}

def prompt_injection_rule(text):
    if 'ignore previous instructions' in text.lower():
        return {'passed': False, 'reason': 'Prompt injection detected'}
    return {'passed': True, 'reason': None}

# Output moderation rules

def toxicity_threshold_rule(text):
    toxic_words = ['hate', 'stupid', 'idiot', 'dumb', 'kill', 'ugly', 'fool', 'trash', 'nonsense', 'worthless', 'pathetic']
    if any(word in text.lower() for word in toxic_words):
        return {'passed': False, 'reason': 'Toxicity detected'}
    return {'passed': True, 'reason': None}

def hallucination_filter_rule(text):
    if 'as an ai' in text.lower() and 'cannot verify' in text.lower():
        return {'passed': False, 'reason': 'Possible hallucination'}
    return {'passed': True, 'reason': None}
