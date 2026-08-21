"""NLP Layer — Chinese text understanding for AI Manga Studio.

Sprint 8.0: Chinese NLP Foundation
- chinese_ner: name extraction with jieba segmentation + title association
- chinese_segmenter: scene splitting via chapter markers, paragraph gaps, transition words
- emotion_mapper: Chinese emotion/action keyword mapping for Director context
"""

from backend.nlp.chinese_ner import ChineseExtractor
from backend.nlp.chinese_segmenter import ChineseSceneParser
from backend.nlp.emotion_mapper import EmotionMapper

__all__ = ["ChineseExtractor", "ChineseSceneParser", "EmotionMapper"]
