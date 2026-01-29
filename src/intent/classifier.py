"""
Intent Classifier - ML-based intent detection (Naive Bayes).
Per AGENTS.md § 5 (Score-Based Routing).

Classifies user prompts as: chit_chat, ebs_control, ambiguous, unknown
Uses Naive Bayes with TF-IDF vectorization.
"""

import logging
from typing import NamedTuple, Optional
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


class IntentClassificationResult(NamedTuple):
    """Result of intent classification"""
    intent: str  # one of: chit_chat, ebs_control, ambiguous, unknown
    confidence: float  # 0.0-1.0
    all_scores: dict  # {class_name: score}


class IntentClassifier:
    """
    ML-based intent classifier using Naive Bayes + TF-IDF.
    
    Per AGENTS.md § 5 (Score-Based Routing):
    - Chit-chat: confidence > 80% => generic Ollama response
    - EBS-Control: confidence > 60% => route to catalog controls
    - Ambiguous: 30% < confidence < 60% => ask clarification
    - Unknown: confidence < 30% => generic response
    """
    
    CHIT_CHAT_THRESHOLD = 0.80
    EBS_CONTROL_THRESHOLD = 0.60
    AMBIGUOUS_THRESHOLD = 0.30

    # Intent class indices
    CHIT_CHAT_CLASS = 0
    EBS_CONTROL_CLASS = 1

    def __init__(self, catalog=None):
        """
        Initialize classifier with training data from catalog keywords.
        
        Args:
            catalog: ControlCatalog instance (optional, for training)
        """
        self.vectorizer = None
        self.classifier = None
        self.classes = ["chit_chat", "ebs_control"]

        if catalog:
            self._train_from_catalog(catalog)
        else:
            self._train_default()

    def _train_default(self):
        """Train classifier with hardcoded training data (fallback)"""
        logger.info("Training IntentClassifier with default data...")

        # Positive samples (EBS-related)
        ebs_samples = [
            "concurrent manager health",
            "concurrent manager durumu",
            "concurrent yönetici sağlık",
            "invalid objects nedir",
            "geçersiz nesneler",
            "adop status",
            "yama uygulaması durumu",
            "workflow queue",
            "iş akışı kuyruğu",
            "active users",
            "aktif kullanıcılar",
            "database objects",
            "plsql compilation error",
            "queue size",
            "request pending",
            "patch application",
            "system health check",
            "process status",
            "session timeout",
            "user session",
        ]

        # Negative samples (generic chit-chat)
        chit_chat_samples = [
            "hello how are you",
            "good morning",
            "what is your name",
            "merhaba nasılsın",
            "günaydin",
            "adın ne",
            "weather today",
            "hava nasıl",
            "favorite color",
            "en sevdiğin renk",
            "tell me a joke",
            "şaka yap",
            "how to cook",
            "yemek pişirme",
            "sports news",
            "spor haberleri",
            "music recommendation",
            "müzik önerisi",
            "travel advice",
            "seyahat tavsiyesi",
        ]

        # Create training data
        X_train = ebs_samples + chit_chat_samples
        y_train = (
            [self.EBS_CONTROL_CLASS] * len(ebs_samples)
            + [self.CHIT_CHAT_CLASS] * len(chit_chat_samples)
        )

        # Vectorize
        self.vectorizer = TfidfVectorizer(
            max_features=100,
            ngram_range=(1, 2),
            lowercase=True,
            stop_words=None,
        )
        X_vec = self.vectorizer.fit_transform(X_train)

        # Train classifier
        self.classifier = MultinomialNB(alpha=0.1)
        self.classifier.fit(X_vec, y_train)

        logger.info(
            f"✓ IntentClassifier trained: {len(ebs_samples)} EBS + "
            f"{len(chit_chat_samples)} chit-chat samples"
        )

    def _train_from_catalog(self, catalog):
        """Train classifier using keywords from control catalog"""
        logger.info("Training IntentClassifier from catalog keywords...")

        # Extract EBS keywords from catalog
        ebs_samples = []
        for control in catalog.get_all_controls():
            ebs_samples.extend(control.keywords.en)
            ebs_samples.extend(control.keywords.tr)

        # Generic chit-chat samples
        chit_chat_samples = [
            "hello",
            "good morning",
            "what is your name",
            "how are you",
            "merhaba",
            "günaydin",
            "nasılsın",
            "adın ne",
            "tell me a joke",
            "şaka yap",
            "weather",
            "hava",
            "sports",
            "spor",
            "music",
            "müzik",
        ]

        # Create training data
        X_train = ebs_samples + chit_chat_samples
        y_train = (
            [self.EBS_CONTROL_CLASS] * len(ebs_samples)
            + [self.CHIT_CHAT_CLASS] * len(chit_chat_samples)
        )

        # Vectorize
        self.vectorizer = TfidfVectorizer(
            max_features=200,
            ngram_range=(1, 2),
            lowercase=True,
            stop_words=None,
        )
        X_vec = self.vectorizer.fit_transform(X_train)

        # Train classifier
        self.classifier = MultinomialNB(alpha=0.1)
        self.classifier.fit(X_vec, y_train)

        logger.info(
            f"✓ IntentClassifier trained from catalog: "
            f"{len(ebs_samples)} EBS keywords + "
            f"{len(chit_chat_samples)} chit-chat samples"
        )

    def classify(self, user_prompt: str) -> IntentClassificationResult:
        """
        Classify user prompt intent with confidence scores.
        
        Args:
            user_prompt: User's input text
            
        Returns:
            IntentClassificationResult with:
            - intent: one of [chit_chat, ebs_control, ambiguous, unknown]
            - confidence: float (0.0-1.0)
            - all_scores: {class: score}
        """
        if not self.vectorizer or not self.classifier:
            raise RuntimeError("Classifier not trained")

        # Vectorize prompt
        X_vec = self.vectorizer.transform([user_prompt])

        # Get probabilities for all classes
        proba = self.classifier.predict_proba(X_vec)[0]
        chit_chat_score = proba[self.CHIT_CHAT_CLASS]
        ebs_control_score = proba[self.EBS_CONTROL_CLASS]

        all_scores = {
            "chit_chat": float(chit_chat_score),
            "ebs_control": float(ebs_control_score),
        }

        # Determine intent and confidence using thresholds
        # Per AGENTS.md § 5 (Score-Based Routing)
        if ebs_control_score > self.EBS_CONTROL_THRESHOLD:
            intent = "ebs_control"
            confidence = ebs_control_score
        elif chit_chat_score > self.CHIT_CHAT_THRESHOLD:
            intent = "chit_chat"
            confidence = chit_chat_score
        elif max(chit_chat_score, ebs_control_score) > self.AMBIGUOUS_THRESHOLD:
            intent = "ambiguous"
            confidence = max(chit_chat_score, ebs_control_score)
        else:
            intent = "unknown"
            confidence = max(chit_chat_score, ebs_control_score)

        logger.debug(
            f"Intent classification: intent={intent}, confidence={confidence:.2%}, "
            f"scores={all_scores}"
        )

        return IntentClassificationResult(
            intent=intent,
            confidence=float(confidence),
            all_scores=all_scores,
        )

    def save(self, filepath: str):
        """Save trained classifier to file"""
        model_state = {
            "vectorizer": self.vectorizer,
            "classifier": self.classifier,
            "classes": self.classes,
        }
        with open(filepath, "wb") as f:
            pickle.dump(model_state, f)
        logger.info(f"✓ Classifier saved to {filepath}")

    def load(self, filepath: str):
        """Load trained classifier from file"""
        with open(filepath, "rb") as f:
            model_state = pickle.load(f)
        self.vectorizer = model_state["vectorizer"]
        self.classifier = model_state["classifier"]
        self.classes = model_state["classes"]
        logger.info(f"✓ Classifier loaded from {filepath}")
