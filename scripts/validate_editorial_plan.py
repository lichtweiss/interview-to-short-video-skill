#!/usr/bin/env python3
"""Validate an interview editorial plan before preview and promotion to formal delivery.

The checker validates editorial evidence and state, not the pixels or audio in a
rendered video. Exit 0 means the plan is internally consistent for its stage;
exit 1 reports blocking errors.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

STAGES = {"candidate", "preview", "formal", "delivered"}
LAYOUTS = {"solo", "two_shot", "wide"}
RELATIONS = {"question_response", "agreement", "contrast", "clarification", "exchange", "other"}
REVIEW_KEYS = ("identity", "audio", "semantic", "visual")
PLACEHOLDER = re.compile(r"^(?:第?\s*\d+\s*段|chapter\s*\d+|segment\s*\d+|0?\d)$", re.I)


class PlanError:
    def __init__(self, path, message):
        self.path = path
        self.message = message

    def as_dict(self):
        return {"path": self.path, "message": self.message}


def read_plan(path):
    raw = sys.stdin.read() if str(path) == "-" else Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError("plan root must be a JSON object")
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def add(errors, path, message):
    errors.append(PlanError(path, message))


def _corrections(plan, errors):
    corrections = plan.get("name_corrections", [])
    if corrections is None:
        corrections = []
    if not isinstance(corrections, list):
        add(errors, "name_corrections", "must be a list when present")
        corrections = []
    correction_pairs = []
    for i, correction in enumerate(corrections):
        path = f"name_corrections[{i}]"
        if not isinstance(correction, dict):
            add(errors, path, "must be an object")
            continue
        wrong, correct = correction.get("wrong"), correction.get("correct")
        if not nonempty(wrong) or not nonempty(correct) or wrong == correct:
            add(errors, path, "requires distinct non-empty wrong and correct names")
        if not nonempty(correction.get("source")):
            add(errors, f"{path}.source", "record where the user correction came from")
        if nonempty(wrong) and nonempty(correct) and wrong != correct:
            correction_pairs.append((wrong, correct))
    return correction_pairs


def _identities(plan, errors, correction_pairs):
    identity_map = plan.get("identity_map")
    people = {}
    names = {}
    if not isinstance(identity_map, list) or not identity_map:
        add(errors, "identity_map", "required, even when a clip later uses only one speaker")
        identity_map = []
    for i, person in enumerate(identity_map):
        path = f"identity_map[{i}]"
        if not isinstance(person, dict):
            add(errors, path, "must be an object")
            continue
        pid = person.get("person_id")
        public_name = person.get("public_name")
        if not nonempty(pid):
            add(errors, f"{path}.person_id", "required and must be stable across clips")
        elif pid in people:
            add(errors, f"{path}.person_id", f"duplicates {pid!r}")
        else:
            people[pid] = person
        if public_name:
            if not nonempty(public_name):
                add(errors, f"{path}.public_name", "must be non-empty when present")
            elif public_name in names:
                add(errors, f"{path}.public_name", f"duplicates {public_name!r}")
            else:
                names[public_name] = pid
            for wrong, correct in correction_pairs:
                if public_name == wrong:
                    add(
                        errors,
                        f"{path}.public_name",
                        f"uses corrected name {wrong!r}; use {correct!r}",
                    )
        if not isinstance(person.get("status"), str) or person.get("status") not in {
            "pending",
            "confirmed",
            "rejected",
        }:
            add(errors, f"{path}.status", "must be pending, confirmed, or rejected")
        if person.get("status") == "confirmed":
            if not nonempty(person.get("confirmed_by")):
                add(errors, f"{path}.confirmed_by", "required for a confirmed identity")
            evidence = person.get("evidence")
            if not isinstance(evidence, dict) or not any(
                nonempty(evidence.get(k)) for k in ("voice", "visual", "source_ref")
            ):
                add(errors, f"{path}.evidence", "include voice, visual, or source_ref evidence")
        if person.get("correction") and not nonempty(person.get("correction_note")):
            add(
                errors,
                f"{path}.correction_note",
                "explain a user correction when correction is present",
            )
    return people


def _themes(plan, errors):
    themes = plan.get("themes")
    theme_ids = set()
    if not isinstance(themes, list) or not themes:
        add(errors, "themes", "provide semantic theme groups, even for one theme")
        themes = []
    for i, theme in enumerate(themes):
        if (
            not isinstance(theme, dict)
            or not nonempty(theme.get("id"))
            or not nonempty(theme.get("name"))
        ):
            add(errors, f"themes[{i}]", "requires non-empty id and name")
            continue
        if theme["id"] in theme_ids:
            add(errors, f"themes[{i}].id", "duplicate theme")
        theme_ids.add(theme["id"])
    return theme_ids


def _clip_membership(clip, path, errors, theme_ids, group_orders, clip_ids):
    cid = clip.get("id")
    if not nonempty(cid):
        add(errors, f"{path}.id", "required")
    elif cid in clip_ids:
        add(errors, f"{path}.id", f"duplicates {cid!r}")
    else:
        clip_ids.add(cid)
    theme_id = clip.get("theme_id")
    if not nonempty(theme_id) or theme_id not in theme_ids:
        add(errors, f"{path}.theme_id", "must reference a declared theme")
    order = clip.get("series_order")
    if type(order) is not int or order < 1:
        add(errors, f"{path}.series_order", "must be a positive integer within the theme")
    elif nonempty(theme_id):
        if (theme_id, order) in group_orders:
            add(errors, f"{path}.series_order", "duplicate order within theme")
        group_orders.add((theme_id, order))
    if not nonempty(clip.get("theme_basis")):
        add(errors, f"{path}.theme_basis", "record why this clip belongs to this theme")


def _clip_text(clip, path, errors, correction_pairs):
    for key in ("topic_id", "title", "selection_reason"):
        if not nonempty(clip.get(key)):
            add(errors, f"{path}.{key}", "required")
    for field in ("title", "subtitle", "descriptor", "footer", "display_name", "speaker_name"):
        value = clip.get(field)
        if isinstance(value, str):
            for wrong, correct in correction_pairs:
                if wrong in value:
                    add(
                        errors,
                        f"{path}.{field}",
                        f"contains corrected name {wrong!r}; use {correct!r}",
                    )


def _windows(clip, path, errors):
    windows = clip.get("source_windows")
    if not isinstance(windows, list) or not windows:
        add(errors, f"{path}.source_windows", "provide at least one source window")
    else:
        for j, window in enumerate(windows):
            if (
                not isinstance(window, dict)
                or not number(window.get("start"))
                or not number(window.get("end"))
                or not 0 <= window["start"] < window["end"]
            ):
                add(errors, f"{path}.source_windows[{j}]", "requires numeric start < end")
    return windows


def _dialogue(clip, path, errors, people, used_people):
    speakers = clip.get("speakers")
    if not isinstance(speakers, list) or not speakers:
        add(errors, f"{path}.speakers", "required stable person_id list")
        speakers = []
    else:
        try:
            repeated = len(speakers) != len(set(speakers))
        except TypeError:
            repeated = False
            add(errors, f"{path}.speakers", "each speaker must be a string person_id")
        if repeated:
            add(errors, f"{path}.speakers", "must not repeat a person")
    for speaker in speakers:
        if not nonempty(speaker):
            add(errors, f"{path}.speakers", "each speaker must be a non-empty person_id")
            continue
        used_people.add(speaker)
        if speaker not in people:
            add(errors, f"{path}.speakers", f"unknown person_id {speaker!r}")
    multi = len(speakers) >= 2
    if not nonempty(clip.get("selection_basis")):
        add(errors, f"{path}.selection_basis", "say why the topic/dialogue unit was selected")
    elif clip["selection_basis"] in {"person_quota", "person_first", "speaker_quota"}:
        add(
            errors,
            f"{path}.selection_basis",
            "person quota is not a valid editorial basis; select by topic and dialogue",
        )
    if multi:
        relation = clip.get("dialogue_relation")
        if not isinstance(relation, str) or relation not in RELATIONS:
            add(
                errors,
                f"{path}.dialogue_relation",
                f"required for multi-person clips; use one of {sorted(RELATIONS)}",
            )
        if not nonempty(clip.get("interaction_summary")):
            add(
                errors,
                f"{path}.interaction_summary",
                "describe the question, response, agreement, contrast, or clarification",
            )
    return speakers


def _composition(clip, path, errors, speakers):
    multi = len(speakers) >= 2
    layout = clip.get("layout")
    if not isinstance(layout, str) or layout not in LAYOUTS:
        add(errors, f"{path}.layout", f"must be one of {sorted(LAYOUTS)}")
    if multi and layout == "solo":
        if not nonempty(clip.get("current_speaker")) or clip.get("current_speaker") not in speakers:
            add(
                errors,
                f"{path}.current_speaker",
                "required and must be one of speakers when a multi-person clip uses solo layout",
            )
        if not nonempty(clip.get("solo_reason")):
            add(errors, f"{path}.solo_reason", "explain why the solo cut preserves the interaction")
    if multi and layout in ("two_shot", "wide") and clip.get("interaction_visible") is not True:
        add(
            errors,
            f"{path}.interaction_visible",
            "must be true when the layout is used to preserve interaction",
        )
    composition = clip.get("composition")
    if not isinstance(composition, dict):
        add(errors, f"{path}.composition", "required with subject_centered/interaction evidence")
    else:
        if layout == "solo" and composition.get("subject_centered") is not True:
            add(
                errors,
                f"{path}.composition.subject_centered",
                "must be true for a solo speaking subject",
            )
        if layout in ("two_shot", "wide") and composition.get("interaction_visible") is not True:
            add(
                errors,
                f"{path}.composition.interaction_visible",
                "must be true for a conversational frame",
            )
        if not nonempty(composition.get("evidence")):
            add(
                errors,
                f"{path}.composition.evidence",
                "record the frame/sample used to choose the composition",
            )
    if "crop" in clip:
        crop = clip["crop"]
        if (
            not isinstance(crop, list)
            or len(crop) != 4
            or not all(type(v) is int for v in crop)
            or min(crop[0], crop[1]) < 0
            or min(crop[2], crop[3]) <= 0
        ):
            add(errors, f"{path}.crop", "must be [x, y, width, height] with positive dimensions")
        if not nonempty(clip.get("crop_evidence")):
            add(
                errors,
                f"{path}.crop_evidence",
                "required; do not rely on a hard-coded left/right crop",
            )


def _chapters(clip, path, errors, windows):
    chapters = clip.get("chapters")
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 3:
        add(errors, f"{path}.chapters", "provide 1-3 semantic chapters")
        chapters = []
    if chapters:
        if not isinstance(chapters[0], dict) or chapters[0].get("start") != 0:
            add(errors, f"{path}.chapters[0].start", "first chapter must start at 0")
        previous = -1
        for j, chapter in enumerate(chapters):
            cpath = f"{path}.chapters[{j}]"
            if not isinstance(chapter, dict):
                add(errors, cpath, "must be an object")
                continue
            start = chapter.get("start")
            if not number(start) or start < 0 or start <= previous:
                add(errors, f"{cpath}.start", "must be numeric and strictly increasing")
            previous = start if number(start) else previous
            if (
                number(start)
                and isinstance(windows, list)
                and windows
                and all(
                    isinstance(w, dict)
                    and number(w.get("start"))
                    and number(w.get("end"))
                    and 0 <= w["start"] < w["end"]
                    for w in windows
                )
            ):
                if start >= sum(w["end"] - w["start"] for w in windows):
                    add(errors, f"{cpath}.start", "chapter must be inside retained source duration")
            if not nonempty(chapter.get("label")):
                add(errors, f"{cpath}.label", "required")
            elif PLACEHOLDER.fullmatch(chapter["label"].strip()):
                add(
                    errors,
                    f"{cpath}.label",
                    "placeholder chapter labels are not semantic editorial decisions",
                )
            if not nonempty(chapter.get("semantic_basis")):
                add(
                    errors,
                    f"{cpath}.semantic_basis",
                    "state the content turn that begins this chapter",
                )
    return len(chapters)


def _reviews(clip, path, errors):
    if not isinstance(clip.get("copy_status"), str) or clip.get("copy_status") not in {
        "draft",
        "user-confirmed",
        "rejected",
    }:
        add(errors, f"{path}.copy_status", "must be draft, user-confirmed, or rejected")
    if not isinstance(clip.get("machine_qc"), str) or clip.get("machine_qc") not in {
        "pending",
        "passed",
        "failed",
    }:
        add(errors, f"{path}.machine_qc", "must be pending, passed, or failed")
    human = clip.get("human_review")
    if not isinstance(human, dict):
        add(errors, f"{path}.human_review", "required; keep human review separate from machine_qc")
    else:
        for key in REVIEW_KEYS:
            if not isinstance(human.get(key), str) or human.get(key) not in {
                "pending",
                "approved",
                "rejected",
            }:
                add(errors, f"{path}.human_review.{key}", "must be pending, approved, or rejected")


def _batch(plan, clips, chapter_counts, errors):
    if len(clips) > 1:
        audit = plan.get("batch_audit")
        if not isinstance(audit, dict) or audit.get("chapter_reviewed") is not True:
            add(
                errors,
                "batch_audit.chapter_reviewed",
                "required true for a batch; review every clip's chapter count",
            )
        if chapter_counts and all(count == 1 for count in chapter_counts):
            if (
                not isinstance(audit, dict)
                or audit.get("uniform_single_chapter_decision") != "accepted_after_review"
                or not nonempty(audit.get("uniform_single_chapter_justification"))
            ):
                add(
                    errors,
                    "batch_audit.uniform_single_chapter_justification",
                    "all-single chapter batches require an explicit semantic justification",
                )


def _state(plan, stage, errors):
    state = plan.get("state")
    if not isinstance(state, dict):
        add(errors, "state", "required canonical delivery state")
        state = {}
    if state.get("conflicting_manifests"):
        add(errors, "state.conflicting_manifests", "must be empty; keep one canonical manifest")
    if not isinstance(state.get("status"), str) or state.get("status") not in STAGES:
        add(errors, "state.status", f"required and must be one of {sorted(STAGES)}")
    if stage in {"formal", "delivered"} and not nonempty(state.get("canonical_manifest")):
        add(errors, "state.canonical_manifest", "required before promotion to formal")
    if isinstance(stage, str) and isinstance(state.get("status"), str) and state["status"] != stage:
        add(errors, "state.status", f"must match requested stage {stage!r}")


def _promotion(plan, stage, clips, people, used_people, errors):
    source_registry = plan.get("source_registry")
    if stage in {"formal", "delivered"}:
        if not isinstance(source_registry, list) or not source_registry:
            add(
                errors,
                "source_registry",
                "formal promotion requires at least one registered source",
            )
        else:
            for i, source in enumerate(source_registry):
                path = f"source_registry[{i}]"
                if not isinstance(source, dict) or not nonempty(source.get("source_ref")):
                    add(errors, path, "requires a non-empty source_ref")
                if isinstance(source, dict) and not nonempty(source.get("sha256")):
                    add(
                        errors,
                        f"{path}.sha256",
                        "record the source fingerprint before promotion to formal",
                    )

    copy_confirmation = plan.get("copy_confirmation")
    if stage in {"formal", "delivered"}:
        if (
            not isinstance(copy_confirmation, dict)
            or copy_confirmation.get("status") != "user-confirmed"
            or not nonempty(copy_confirmation.get("revision_id"))
        ):
            add(
                errors,
                "copy_confirmation",
                "formal promotion requires user-confirmed status and revision_id",
            )
    for i, speaker in enumerate(sorted(used_people)):
        person = people.get(speaker)
        if stage in {"formal", "delivered"} and (not person or person.get("status") != "confirmed"):
            add(
                errors,
                f"identity_map[{speaker}]",
                "every speaker used in formal clips must be user-confirmed",
            )
    if stage in {"formal", "delivered"}:
        for i, clip in enumerate(clips):
            if not isinstance(clip, dict):
                continue
            path = f"clips[{i}]"
            if clip.get("copy_status") != "user-confirmed":
                add(errors, f"{path}.copy_status", "formal promotion requires user-confirmed copy")
            if clip.get("machine_qc") != "passed":
                add(errors, f"{path}.machine_qc", "formal promotion requires passed machine QC")
            human = clip.get("human_review", {})
            if not isinstance(human, dict):
                human = {}
            for key in REVIEW_KEYS:
                if human.get(key) != "approved":
                    add(
                        errors,
                        f"{path}.human_review.{key}",
                        "formal delivery requires explicit human approval",
                    )


def validate(plan, requested_stage=None):
    errors = []
    if not isinstance(plan, dict):
        add(errors, "plan", "must be an object")
        return errors
    stage = requested_stage if requested_stage is not None else plan.get("stage", "preview")
    if not isinstance(stage, str) or stage not in STAGES:
        add(errors, "stage", f"must be one of {sorted(STAGES)}")
        stage = "invalid"
    correction_pairs = _corrections(plan, errors)
    people = _identities(plan, errors, correction_pairs)
    theme_ids = _themes(plan, errors)
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        add(errors, "clips", "required and must contain at least one clip")
        clips = []
    group_orders, clip_ids, used_people = set(), set(), set()
    chapter_counts = []
    for i, clip in enumerate(clips):
        path = f"clips[{i}]"
        if not isinstance(clip, dict):
            add(errors, path, "must be an object")
            continue
        _clip_membership(clip, path, errors, theme_ids, group_orders, clip_ids)
        _clip_text(clip, path, errors, correction_pairs)
        windows = _windows(clip, path, errors)
        speakers = _dialogue(clip, path, errors, people, used_people)
        _composition(clip, path, errors, speakers)
        chapter_counts.append(_chapters(clip, path, errors, windows))
        _reviews(clip, path, errors)
    _batch(plan, clips, chapter_counts, errors)
    _state(plan, stage, errors)
    _promotion(plan, stage, clips, people, used_people, errors)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="JSON plan path, or - for stdin")
    parser.add_argument("--stage", choices=sorted(STAGES), help="override plan.stage")
    parser.add_argument("--json", action="store_true", help="emit machine-readable result")
    args = parser.parse_args()
    try:
        plan = read_plan(args.plan)
    except (OSError, ValueError) as exc:
        result = {"valid": False, "errors": [{"path": "plan", "message": str(exc)}]}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL plan: {exc}", file=sys.stderr)
        return 1
    errors = validate(plan, args.stage)
    result = {
        "valid": not errors,
        "stage": args.stage or plan.get("stage", "preview"),
        "errors": [e.as_dict() for e in errors],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print(f"FAIL {len(errors)} editorial plan error(s):")
        for error in errors:
            print(f"- {error.path}: {error.message}")
    else:
        print(f"PASS editorial plan ({result['stage']})")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
