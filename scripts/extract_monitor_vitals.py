#!/usr/bin/env python3
"""
Monitor OCR & Vital Signs Extraction Module
Extracts vital signs from patient monitor video (monitor.mp4)
"""

import os
import json
import argparse
import re
from pathlib import Path

from scripts.utils.session_paths import raw_dir, videos_dir


def iter_sampled_frames(capture, frame_interval):
    """Yield the same indexed frames as a read-every-frame modulo loop.

    ``VideoCapture.read()`` is ``grab()`` followed by ``retrieve()``. Advancing every
    frame with grab preserves decoder state, while skipping retrieve avoids converting
    discarded frames into pixel arrays.
    """
    frame_num = 0
    while capture.isOpened():
        if not capture.grab():
            return
        if frame_num % frame_interval == 0:
            retrieved, frame = capture.retrieve()
            if not retrieved:
                return
            yield frame_num, frame
        frame_num += 1

# Physiologically possible readings for a living patient, used only to reject OCR
# misreads. Deliberately wider than any clinical alarm threshold: the job here is to
# distinguish "the camera read a digit wrong" from "the patient is deteriorating", and
# only the first should be discarded. nbp_mean has no entry because the monitor renders
# it parenthesised and it is not alarm-checked.
# Vitals extracted for context but deliberately not alarm-checked. nbp_mean is a
# derived mean the monitor renders parenthesised; the systolic and diastolic
# values it summarises are thresholded individually.
# The numeric vitals extract_vitals_from_frame produces. Anomaly detection walks this
# set, so metadata the caller attaches alongside them is never mistaken for a reading.
EXTRACTED_VITALS = (
    "hr", "spo2", "nbp_sys", "nbp_dia", "nbp_mean", "pulse", "resp_rate", "temp",
)

UNTHRESHOLDED_VITALS = frozenset({"nbp_mean"})

PLAUSIBLE_VITAL_RANGE = {
    "hr": (25, 250),
    "pulse": (25, 250),
    "spo2": (60, 100),
    "nbp_sys": (50, 250),
    "nbp_dia": (20, 150),
    "nbp_mean": (30, 200),
    "resp_rate": (4, 60),
    "temp": (33.0, 42.5),
}


class MonitorVitalsExtractor:
    """Extract vital signs from patient monitor video"""

    def __init__(self, config, device='cuda'):
        if config.get("schema_version") != "1.0.0":
            raise ValueError("Monitor OCR config must declare schema_version 1.0.0")
        if not config.get("rois") or not config.get("thresholds"):
            raise ValueError("Monitor OCR config requires explicit rois and thresholds")
        global cv2, easyocr, tqdm
        import cv2
        import easyocr
        from tqdm import tqdm
        print("Initializing EasyOCR...")
        self.reader = easyocr.Reader(['en'], gpu=(device == 'cuda'))
        self.rois = {name: tuple(bounds) for name, bounds in config["rois"].items()}
        self.thresholds = config["thresholds"]

    def extract_text_from_roi(self, frame, roi_name):
        """Extract text from a specific ROI"""
        if roi_name not in self.rois:
            # A name this code asks for but the config does not define is a contract
            # mismatch, not an empty reading. Returning "" made them identical, and
            # blood pressure was silently never extracted because the config calls it
            # nbp_sys/nbp_dia while this code asked for bp_sys/bp_dia.
            raise KeyError(
                f"monitor config defines no ROI named {roi_name!r}; "
                f"configured ROIs: {sorted(self.rois)}"
            )

        x, y, w, h = self.rois[roi_name]

        # Ensure ROI is within frame bounds
        frame_h, frame_w = frame.shape[:2]
        x = max(0, min(x, frame_w - 1))
        y = max(0, min(y, frame_h - 1))
        w = min(w, frame_w - x)
        h = min(h, frame_h - y)

        roi = frame[y:y+h, x:x+w]

        # Preprocess ROI for better OCR
        # Convert to grayscale if not already
        if len(roi.shape) == 3:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            roi_gray = roi

        # Enhance contrast
        roi_enhanced = cv2.equalizeHist(roi_gray)

        # OCR
        result = self.reader.readtext(roi_enhanced, detail=0)
        text = " ".join(result)

        return text.strip()

    def parse_vital_value(self, text, vital_type):
        """Parse numeric value from OCR text"""
        if not text:
            return None

        # Normalise comma decimal separators before extracting numbers. Without this,
        # "38,0" splits into ['38', '0'] and the last-number rule below returns 0.0,
        # turning a normal reading into a critical-low alarm.
        text = re.sub(r'(?<=\d),(?=\d)', '.', text)

        # Remove non-numeric characters except decimal point
        numbers = re.findall(r'\d+\.?\d*', text)

        if not numbers:
            return None

        # Take the LAST number found (skip labels like "100" scale markers)
        # For vitals, the actual value is usually the last/largest number
        try:
            value = float(numbers[-1])

            # Reject readings outside what a living patient can produce. These are OCR
            # plausibility bounds, NOT the clinical alarm thresholds in the config: a
            # value here is rejected as a misread, whereas a value outside an alarm
            # threshold is a real finding. Keeping them apart matters because a clipped
            # digit otherwise becomes a critical alarm -- a respiratory rate ROI that
            # captured only the first digit of "24" reported 2 in 82% of samples and
            # produced the single largest source of flags in the session.
            bounds = PLAUSIBLE_VITAL_RANGE.get(vital_type)
            if bounds is not None:
                low, high = bounds
                if not (low <= value <= high):
                    return None

            return value
        except ValueError:
            return None

    def extract_vitals_from_frame(self, frame):
        """Extract all vitals from a single frame"""
        vitals = {}

        # Extract alert banner
        alert_text = self.extract_text_from_roi(frame, "alert_banner")
        if alert_text:
            vitals["alert"] = alert_text

        # Extract numeric vitals
        hr_text = self.extract_text_from_roi(frame, "hr")
        vitals["hr"] = self.parse_vital_value(hr_text, "hr")

        spo2_text = self.extract_text_from_roi(frame, "spo2")
        vitals["spo2"] = self.parse_vital_value(spo2_text, "spo2")

        # NBP is what the monitor labels these, and what the config and thresholds
        # call them. The previous bp_* spelling matched nothing on either side.
        nbp_sys_text = self.extract_text_from_roi(frame, "nbp_sys")
        vitals["nbp_sys"] = self.parse_vital_value(nbp_sys_text, "nbp_sys")

        nbp_dia_text = self.extract_text_from_roi(frame, "nbp_dia")
        vitals["nbp_dia"] = self.parse_vital_value(nbp_dia_text, "nbp_dia")

        nbp_mean_text = self.extract_text_from_roi(frame, "nbp_mean")
        vitals["nbp_mean"] = self.parse_vital_value(nbp_mean_text, "nbp_mean")

        pulse_text = self.extract_text_from_roi(frame, "pulse")
        vitals["pulse"] = self.parse_vital_value(pulse_text, "pulse")

        resp_text = self.extract_text_from_roi(frame, "resp_rate")
        vitals["resp_rate"] = self.parse_vital_value(resp_text, "resp_rate")

        temp_text = self.extract_text_from_roi(frame, "temp")
        vitals["temp"] = self.parse_vital_value(temp_text, "temp")

        return vitals

    def detect_anomalies(self, vitals):
        """Detect anomalies in vital signs"""
        anomalies = []

        # Iterate the declared vitals rather than whatever keys the mapping happens to
        # carry: callers add non-vital metadata (process_video attaches timestamp and
        # frame_num before calling here), and treating those as vitals made this raise
        # on the first frame of every session.
        for vital_name in EXTRACTED_VITALS:
            value = vitals.get(vital_name)
            if value is None:
                continue

            if vital_name not in self.thresholds:
                # Skipping silently is what let blood pressure go unchecked: the code
                # emitted bp_sys while the thresholds were keyed nbp_sys, so every
                # reading fell through here unnoticed. Only vitals declared as having
                # no alarm band may skip; anything else is a configuration mismatch.
                if vital_name in UNTHRESHOLDED_VITALS:
                    continue
                raise KeyError(
                    f"vital {vital_name!r} has no configured threshold and is not "
                    f"declared in UNTHRESHOLDED_VITALS; configured: "
                    f"{sorted(self.thresholds)}"
                )

            thresholds = self.thresholds[vital_name]

            # Check critical thresholds
            if value < thresholds["critical_low"]:
                anomalies.append({
                    "vital": vital_name,
                    "value": value,
                    "severity": "critical",
                    "reason": f"{vital_name} critically low (<{thresholds['critical_low']})"
                })
            elif value > thresholds["critical_high"]:
                anomalies.append({
                    "vital": vital_name,
                    "value": value,
                    "severity": "critical",
                    "reason": f"{vital_name} critically high (>{thresholds['critical_high']})"
                })
            # Check warning thresholds
            elif value < thresholds["low"]:
                anomalies.append({
                    "vital": vital_name,
                    "value": value,
                    "severity": "warning",
                    "reason": f"{vital_name} low (<{thresholds['low']})"
                })
            elif value > thresholds["high"]:
                anomalies.append({
                    "vital": vital_name,
                    "value": value,
                    "severity": "warning",
                    "reason": f"{vital_name} high (>{thresholds['high']})"
                })

        # Check for alert banner
        if "alert" in vitals:
            alert_text = vitals["alert"].upper()
            if any(keyword in alert_text for keyword in ["EXTREME", "CRITICAL", "BRADY", "TACHY", "ALARM"]):
                anomalies.append({
                    "vital": "monitor_alert",
                    "value": vitals["alert"],
                    "severity": "critical",
                    "reason": f"Monitor alert: {vitals['alert']}"
                })

        return anomalies

    def process_video(self, video_path, output_path, sample_rate):
        """
        Process monitor video and extract vitals timeline

        Args:
            video_path: Path to monitor video
            output_path: Path to save JSON output
            sample_rate: Frames per second to sample (1.0 = 1 FPS)
        """
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps

        print(f"Video: {video_path}")
        print(f"  FPS: {fps:.2f}")
        print(f"  Total frames: {total_frames}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Sampling rate: {sample_rate} FPS")

        frame_interval = int(fps / sample_rate)
        if frame_interval < 1:
            raise ValueError(
                f"sample_rate ({sample_rate}) cannot exceed video FPS ({fps})"
            )
        timeline = []
        critical_moments = []

        with tqdm(total=total_frames // frame_interval, desc="Processing frames") as pbar:
            for frame_num, frame in iter_sampled_frames(cap, frame_interval):
                timestamp = frame_num / fps

                vitals = self.extract_vitals_from_frame(frame)
                vitals["timestamp"] = timestamp
                vitals["frame_num"] = frame_num

                # Detect anomalies
                anomalies = self.detect_anomalies(vitals)
                if anomalies:
                    vitals["anomalies"] = anomalies
                    critical_moments.append({
                        "timestamp": timestamp,
                        "vitals": {k: v for k, v in vitals.items() if k not in ["timestamp", "frame_num", "anomalies"]},
                        "anomalies": anomalies,
                        "source": "monitor_ocr"
                    })

                timeline.append(vitals)
                pbar.update(1)

        cap.release()

        # Save results
        output_data = {
            "source_video": str(video_path),
            "duration_seconds": duration,
            "sample_rate_fps": sample_rate,
            "timeline": timeline,
            "critical_moments": critical_moments
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✓ Vitals timeline saved to: {output_path}")
        print(f"  Total samples: {len(timeline)}")
        print(f"  Critical moments detected: {len(critical_moments)}")

        return output_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract vital signs from patient monitor video")
    parser.add_argument("--session-id", required=True,
                        help="Session ID for session-scoped inputs and outputs")
    parser.add_argument("--config", required=True,
                        help="Versioned monitor ROI and threshold JSON")
    parser.add_argument("--sample-rate", type=float, required=True,
                        help="Configured sampling rate in FPS")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="Device for OCR")

    args = parser.parse_args()

    with Path(args.config).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    video = videos_dir(args.session_id) / "monitor.mp4"
    output = raw_dir(args.session_id) / "monitor_vitals.json"

    print("=" * 80)
    print("MONITOR VITAL SIGNS EXTRACTION")
    print("=" * 80)

    extractor = MonitorVitalsExtractor(config, device=args.device)
    extractor.process_video(video, output, args.sample_rate)

    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)
