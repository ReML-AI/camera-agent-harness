#!/usr/bin/env python3
"""Train a role classifier from authorized human labels and tracking data.

The study training inputs are not in this repository. This module
does not download, infer, or synthesize those governed labels.  A newly trained
model is a new artifact and is not expected to match the historical model hash.
"""

import json
import argparse
import hashlib
import numpy as np
from pathlib import Path
import sys
from typing import Dict, List, Sequence, Tuple
import pickle

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay


EMBEDDING_WIDTH = 512
NOT_LABELED = "Not Labeled"
ALLOWED_ROLES = frozenset(
    {
        "Student Nurse (Primary)",
        "Supervising Nurse/Doctor",
        "Patient/Mannequin",
        "Observer/Other",
        "Background/False Detection",
    }
)
HISTORICAL_MODEL_SHA256 = "5fdf04c7b0ba378a4a25f2cbbbe04a84587913667753f00f452b1fed59068b84"


class TrainingDataError(ValueError):
    """The operator-supplied labels or tracking records are not trainable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def operator_input_instructions() -> str:
    return """REQUIRED OPERATOR INPUTS (not present in this repository):
1. An authorized per-camera role-label JSON with a top-level person_labels object.
   Each key must be <camera_id>_person_<person_id>; each value must contain a
   human-assigned role. Do not derive or fabricate clinical roles.
2. The matching person_tracks_*.json files produced from the governed recordings.
   Each file must contain camera_id and persons; every used person needs person_id,
   track_id, total_screen_time_seconds, and a 512-value OSNet embedding. Labels and
   tracks must describe the same training cohort.
3. Either obtain the authorized original models/role_classifier.pkl, or retrain with:
   python3 scripts/role_classification/train_classifier.py \\
     --labels /ABS/PATH/person_roles_per_camera.json \\
     --tracks-dir /ABS/PATH/tracks \\
     --output models/role_classifier.pkl
4. If retraining, validate the new model for the intended cohort and record the label
   and track-file SHA-256 values, dependency versions, command, model SHA-256, and
   validation results. The new pickle is not expected to be byte-identical to the
   historical model, so the historical SHA-256 must not gate the retrained artifact;
   its digest remains capture_at_run until the new bytes are measured."""


class RoleClassifier:
    """Supervised role classifier using appearance and behavioral features."""

    def __init__(self):
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        self.classifier = None
        self.feature_names = []

    def extract_features(self, person_data: Dict, embedding: np.ndarray = None) -> np.ndarray:
        """
        Extract features for classification

        Features include:
        - Appearance embedding (512-dim)
        - Total screen time
        - Number of camera views
        - Screen time variance across cameras
        - Avg screen time per camera
        - Max/min screen time in single camera
        """
        features = []

        # Appearance features (embedding)
        if embedding is not None:
            embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if embedding.shape != (EMBEDDING_WIDTH,):
                raise TrainingDataError(
                    f"appearance embedding must contain exactly {EMBEDDING_WIDTH} values, "
                    f"got {embedding.size}"
                )
            if not np.isfinite(embedding).all():
                raise TrainingDataError("appearance embedding contains a non-finite value")
            features.extend(embedding.tolist())
        else:
            features.extend([0.0] * EMBEDDING_WIDTH)

        # Behavioral features
        total_screen_time = person_data.get('screen_time', 0)
        camera_views = person_data.get('camera_views', 0)
        tracks = person_data.get('tracks', [])

        features.append(total_screen_time)
        features.append(camera_views)

        # Screen time distribution
        if tracks:
            screen_times = [t['screen_time'] for t in tracks]
            features.append(np.mean(screen_times))
            features.append(np.std(screen_times))
            features.append(np.max(screen_times))
            features.append(np.min(screen_times))
            features.append(total_screen_time / camera_views if camera_views > 0 else 0)
        else:
            features.extend([0, 0, 0, 0, 0])

        # Camera coverage features
        features.append(1 if camera_views >= 3 else 0)  # Present in all cameras
        features.append(1 if camera_views == 2 else 0)  # Present in 2 cameras
        features.append(1 if camera_views == 1 else 0)  # Single camera only

        return np.array(features)

    def prepare_training_data(
        self,
        labels_file: str,
        tracks_files: List[str],
        per_camera_mode: bool = True,
        require_embeddings: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepare training data from labeled persons

        Args:
            labels_file: Path to labels JSON
            tracks_files: List of per-camera track files
            per_camera_mode: If True, use per-camera labels (default)

        Returns:
            X: Feature matrix
            y: Labels
            person_ids: List of person IDs
        """
        if not per_camera_mode:
            raise TrainingDataError("only the documented per-camera training mode is supported")
        labels_path = Path(labels_file)
        if not labels_path.is_file():
            raise TrainingDataError(f"role-label JSON is missing: {labels_path}")
        if not tracks_files:
            raise TrainingDataError("no person_tracks_*.json files were supplied")

        try:
            with labels_path.open('r', encoding='utf-8') as f:
                labels_data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise TrainingDataError(f"could not read role-label JSON {labels_path}: {exc}") from exc
        if not isinstance(labels_data, dict) or not isinstance(
            labels_data.get('person_labels'), dict
        ):
            raise TrainingDataError("role-label JSON must contain a person_labels object")

        # Load embeddings and person data from track files
        persons_map = {}
        for track_file in tracks_files:
            track_path = Path(track_file)
            if not track_path.is_file():
                raise TrainingDataError(f"tracking JSON is missing: {track_path}")
            try:
                with track_path.open('r', encoding='utf-8') as f:
                    track_data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise TrainingDataError(f"could not read tracking JSON {track_path}: {exc}") from exc
            if not isinstance(track_data, dict) or not isinstance(track_data.get('persons'), list):
                raise TrainingDataError(f"{track_path} must contain camera_id and a persons array")
            camera_id = track_data.get('camera_id')
            if not isinstance(camera_id, str) or not camera_id:
                raise TrainingDataError(f"{track_path} has no non-empty camera_id")

            for index, person in enumerate(track_data['persons']):
                if not isinstance(person, dict):
                    raise TrainingDataError(f"{track_path} persons[{index}] must be an object")
                missing = [
                    key for key in ('person_id', 'track_id', 'total_screen_time_seconds')
                    if key not in person
                ]
                if missing:
                    raise TrainingDataError(
                        f"{track_path} persons[{index}] is missing fields: {missing}"
                    )
                person_id = person['person_id']
                unique_id = f"{camera_id}_person_{person_id}"
                if unique_id in persons_map:
                    raise TrainingDataError(f"duplicate per-camera person identifier: {unique_id}")
                raw_embedding = person.get('embedding')
                if require_embeddings and raw_embedding is None:
                    raise TrainingDataError(
                        f"{unique_id} has no 512-value OSNet embedding; use "
                        "--allow-missing-embeddings only for an explicitly justified behavior-only model"
                    )
                embedding = None
                if raw_embedding is not None:
                    try:
                        embedding = np.asarray(raw_embedding, dtype=np.float32)
                    except (TypeError, ValueError) as exc:
                        raise TrainingDataError(
                            f"{unique_id} embedding must be a numeric array"
                        ) from exc
                    if embedding.reshape(-1).shape != (EMBEDDING_WIDTH,):
                        raise TrainingDataError(
                            f"{unique_id} embedding has {embedding.size} values; "
                            f"expected {EMBEDDING_WIDTH}"
                        )
                try:
                    screen_time = float(person['total_screen_time_seconds'])
                except (TypeError, ValueError) as exc:
                    raise TrainingDataError(
                        f"{unique_id} total_screen_time_seconds must be numeric"
                    ) from exc
                if not np.isfinite(screen_time) or screen_time < 0:
                    raise TrainingDataError(
                        f"{unique_id} total_screen_time_seconds must be finite and non-negative"
                    )

                persons_map[unique_id] = {
                    'embedding': embedding,
                    'screen_time': screen_time,
                    'camera_views': 1,
                    'tracks': [{
                        'camera_id': camera_id,
                        'track_id': person['track_id'],
                        'screen_time': screen_time
                    }]
                }

        # Build feature matrix
        X = []
        y = []
        person_ids = []

        missing_labeled_people = []
        for unique_id, label_info in labels_data['person_labels'].items():
            if not isinstance(unique_id, str) or not isinstance(label_info, dict):
                raise TrainingDataError("person_labels must map string identifiers to objects")
            role = label_info.get('role')
            if not isinstance(role, str) or not role.strip():
                raise TrainingDataError(f"{unique_id} has no non-empty role")

            # Skip unlabeled
            if role == NOT_LABELED:
                continue
            if role not in ALLOWED_ROLES:
                raise TrainingDataError(
                    f"{unique_id} has unsupported role {role!r}; expected one of "
                    f"{sorted(ALLOWED_ROLES)} or {NOT_LABELED!r}"
                )

            # Get person data
            if unique_id not in persons_map:
                missing_labeled_people.append(unique_id)
                continue

            person_data = persons_map[unique_id]
            embedding = person_data['embedding']

            # Extract features
            features = self.extract_features(person_data, embedding)

            X.append(features)
            y.append(role)
            person_ids.append(unique_id)

        if missing_labeled_people:
            raise TrainingDataError(
                "labeled people are absent from the supplied tracking files: "
                f"{sorted(missing_labeled_people)[:10]}"
            )

        self.feature_names = (
            [f'emb_{i}' for i in range(EMBEDDING_WIDTH)] +
            ['total_screen_time', 'camera_views', 'mean_screen_time',
             'std_screen_time', 'max_screen_time', 'min_screen_time',
             'avg_per_camera', 'all_cameras', 'two_cameras', 'single_camera']
        )

        if not X:
            raise TrainingDataError("no human-labeled training examples remain after validation")
        if len(set(y)) < 2:
            raise TrainingDataError("at least two distinct human-assigned roles are required")
        return np.asarray(X, dtype=np.float64), np.asarray(y), person_ids

    def train(self, X: np.ndarray, y: np.ndarray, model_type='rf'):
        """
        Train classifier

        Args:
            X: Feature matrix
            y: Labels
            model_type: 'rf' (Random Forest) or 'gb' (Gradient Boosting)
        """
        if model_type not in {'rf', 'gb'}:
            raise ValueError("model_type must be 'rf' or 'gb'")
        if X.ndim != 2 or X.shape[1] != EMBEDDING_WIDTH + 10:
            raise TrainingDataError(
                f"training matrix must have {EMBEDDING_WIDTH + 10} features per sample"
            )
        if len(X) != len(y) or len(X) == 0:
            raise TrainingDataError("training features and labels must be non-empty and aligned")

        print(f"\n{'='*80}")
        print("TRAINING ROLE CLASSIFIER")
        print(f"{'='*80}")
        print(f"Training samples: {len(X)}")
        print(f"Features: {X.shape[1]}")
        print(f"Unique roles: {len(np.unique(y))}")
        print("\nRole distribution:")
        for role, count in zip(*np.unique(y, return_counts=True)):
            print(f"  {role}: {count}")

        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)

        # Scale features
        X_scaled = self.scaler.fit_transform(X)

        # Train classifier
        if model_type == 'rf':
            self.classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=2,
                random_state=42,
                class_weight='balanced'
            )
        elif model_type == 'gb':
            self.classifier = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )

        # Cross-validation
        class_counts = np.bincount(y_encoded)
        cv_folds = min(5, len(X), int(class_counts.min()))
        if cv_folds >= 2:
            print(f"\nPerforming {cv_folds}-fold stratified cross-validation...")
            cv_scores = cross_val_score(
                self.classifier,
                X_scaled,
                y_encoded,
                cv=cv_folds,
                scoring='accuracy'
            )
            print(f"CV Accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")
        else:
            print("\nCross-validation skipped: every role needs at least two examples per fold.")

        # Train on full dataset
        print(f"\nTraining {model_type.upper()} classifier...")
        self.classifier.fit(X_scaled, y_encoded)

        # Feature importance
        if hasattr(self.classifier, 'feature_importances_'):
            importances = self.classifier.feature_importances_
            # Get top 20 features
            top_indices = np.argsort(importances)[-20:][::-1]

            print("\nTop 20 Feature Importances:")
            for idx in top_indices:
                print(f"  {self.feature_names[idx]}: {importances[idx]:.4f}")

        print("\n✓ Training complete")

    def predict(self, person_data: Dict, embedding: np.ndarray = None) -> Tuple[str, float]:
        """
        Predict role for a person

        Returns:
            role: Predicted role
            confidence: Prediction confidence (probability)
        """
        features = self.extract_features(person_data, embedding)
        features_scaled = self.scaler.transform([features])

        prediction_encoded = self.classifier.predict(features_scaled)[0]
        probabilities = self.classifier.predict_proba(features_scaled)[0]

        role = self.label_encoder.inverse_transform([prediction_encoded])[0]
        confidence = probabilities[prediction_encoded]

        return role, confidence

    def save(self, output_path: str):
        """Save trained model"""
        model_data = {
            'classifier': self.classifier,
            'scaler': self.scaler,
            'label_encoder': self.label_encoder,
            'feature_names': self.feature_names
        }

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('wb') as f:
            pickle.dump(model_data, f, protocol=4)

        print(f"\n✓ Model saved: {destination}")
        print(f"  SHA-256: {sha256_file(destination)}")

    @classmethod
    def load(cls, model_path: str):
        """Load trained model"""
        with open(model_path, 'rb') as f:
            model_data = pickle.load(f)

        classifier = cls()
        classifier.classifier = model_data['classifier']
        classifier.scaler = model_data['scaler']
        classifier.label_encoder = model_data['label_encoder']
        classifier.feature_names = model_data['feature_names']

        return classifier


def plot_confusion_matrix(y_true, y_pred, labels, output_path):
    """Plot confusion matrix"""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to write the confusion matrix") from exc

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    plt.figure(figsize=(10, 8))
    display = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    display.plot(cmap='Blues', values_format='d', ax=plt.gca(), colorbar=False)
    plt.title('Role Classification Confusion Matrix')
    plt.ylabel('True Role')
    plt.xlabel('Predicted Role')
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"✓ Confusion matrix saved: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train role classifier from authorized per-camera human labels",
        epilog="Run with --explain-inputs to print the governed-input contract.",
    )
    parser.add_argument('--labels', type=str, default='data/labeled/person_roles_per_camera.json',
                       help="Path to labeled persons JSON (per-camera)")
    parser.add_argument('--tracks-dir', type=str, default='data/processed',
                       help="Directory with person track JSON files")
    parser.add_argument('--output', type=str, default='models/role_classifier.pkl',
                       help="Output model path")
    parser.add_argument('--model-type', type=str, default='rf', choices=['rf', 'gb'],
                       help="Classifier type (rf=Random Forest, gb=Gradient Boosting)")
    parser.add_argument(
        '--allow-missing-embeddings',
        action='store_true',
        help=(
            "explicitly train a behavior-only fallback with zero appearance features; "
            "this cannot be assumed equivalent to the historical classifier"
        ),
    )
    parser.add_argument(
        '--explain-inputs',
        action='store_true',
        help="print the exact operator-supplied inputs and provenance requirements, then exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.explain_inputs:
        print(operator_input_instructions())
        return 0

    # Find track files
    tracks_dir = Path(args.tracks_dir)
    track_files = sorted(tracks_dir.glob('person_tracks_*.json'))

    if not track_files:
        print(f"ERROR: no person_tracks_*.json files found in {tracks_dir}", file=sys.stderr)
        print(operator_input_instructions(), file=sys.stderr)
        return 2

    print(f"Found {len(track_files)} track files:")
    for f in track_files:
        print(f"  - {f.name}")

    # Initialize classifier
    classifier = RoleClassifier()

    # Prepare training data
    print("\nPreparing training data (per-camera mode)...")
    try:
        X, y, person_ids = classifier.prepare_training_data(
            args.labels,
            [str(f) for f in track_files],
            per_camera_mode=True,
            require_embeddings=not args.allow_missing_embeddings,
        )
    except TrainingDataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(operator_input_instructions(), file=sys.stderr)
        return 2

    # Train
    classifier.train(X, y, model_type=args.model_type)

    # Save model
    classifier.save(args.output)

    # Generate classification report
    y_pred = classifier.label_encoder.inverse_transform(
        classifier.classifier.predict(classifier.scaler.transform(X))
    )

    print(f"\n{'='*80}")
    print("CLASSIFICATION REPORT")
    print(f"{'='*80}")
    print(classification_report(y, y_pred))

    # Plot confusion matrix
    output_path = Path(args.output)
    plot_output = output_path.with_name(f"{output_path.stem}_confusion_matrix.png")
    plot_confusion_matrix(y, y_pred, classifier.label_encoder.classes_, plot_output)

    print(f"\n{'='*80}")
    print("TRAINING COMPLETE")
    print(f"{'='*80}")
    print("\nModel artifact created; validate it on the intended cohort before runtime use.")
    print("\nINPUT DIGESTS TO RECORD:")
    print(f"labels_sha256={sha256_file(Path(args.labels))}  {Path(args.labels).resolve()}")
    for track_file in track_files:
        print(f"tracks_sha256={sha256_file(track_file)}  {track_file.resolve()}")
    print(f"model_sha256={sha256_file(output_path)}  {output_path.resolve()}")
    print(f"python_version={sys.version.split()[0]}")
    print(f"numpy_version={np.__version__}")
    import sklearn
    print(f"scikit_learn_version={sklearn.__version__}")
    print(f"model_type={args.model_type}")
    print(f"allow_missing_embeddings={args.allow_missing_embeddings}")
    print(
        "This is a newly trained artifact. It is not expected to equal the historical "
        f"SHA-256 {HISTORICAL_MODEL_SHA256}; that historical digest must not gate this model."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
