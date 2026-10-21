"""Persist paired examples and compute gap metrics and tie-aware Spearman rho."""

from collections import defaultdict
from statistics import correlation

from sqlalchemy import select
from sqlalchemy.orm import Session

from .match_schemas import HumanAnnotation, MatchReport, MatchRequest
from .matching import score_dimensions
from .models import MatchCase
from .normalize import canonical


def save_case(session: Session, request: MatchRequest, report: MatchReport) -> None:
    record = session.get(MatchCase, report.case_id)
    if record is None:
        record = MatchCase(
            id=report.case_id,
            resume_data=request.resume.model_dump(),
            job_data=request.job.model_dump(),
            prediction=report.model_dump(),
        )
        session.add(record)
    else:
        record.prediction = report.model_dump()
    session.commit()


def human_score(annotation: HumanAnnotation) -> float:
    dimensions = score_dimensions({item.category: item.score for item in annotation.dimensions})
    return round(sum(item.contribution for item in dimensions), 2)


def annotate_case(session: Session, record: MatchCase, annotation: HumanAnnotation) -> None:
    record.annotation = annotation.model_dump()
    session.commit()


def average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for index in ordered[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def spearman(predicted: list[float], human: list[float]) -> float | None:
    if len(predicted) < 2 or len(set(predicted)) < 2 or len(set(human)) < 2:
        return None
    return round(correlation(average_ranks(predicted), average_ranks(human)), 6)


def compute_metrics(examples: list[dict]) -> dict:
    tp = fp = fn = 0
    predicted_scores, human_scores = [], []
    for example in examples:
        predicted = {canonical(name) for name in example["predicted_gaps"]}
        gold = {canonical(name) for name in example["human_gaps"]}
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
        predicted_scores.append(example["predicted_score"])
        human_scores.append(example["human_score"])
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "pairs": len(examples),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "f1": round(f1, 6) if f1 is not None else None,
        "spearman": spearman(predicted_scores, human_scores),
    }


def evaluation_summary(session: Session) -> dict:
    cases = session.scalars(select(MatchCase)).all()
    labelled = [case for case in cases if case.annotation is not None]
    groups = defaultdict(list)
    for case in labelled:
        annotation = HumanAnnotation.model_validate(case.annotation)
        prediction = case.prediction
        groups[(prediction["model"], prediction["rubric_version"])].append(
            {
                "predicted_gaps": prediction["skill_gaps"],
                "human_gaps": annotation.skill_gaps,
                "predicted_score": prediction["total_score"],
                "human_score": human_score(annotation),
            }
        )
    return {
        "target": 50,
        "total_pairs": len(cases),
        "labelled_pairs": len(labelled),
        "target_reached": any(len(examples) >= 50 for examples in groups.values()),
        "groups": [
            {"model": model, "rubric_version": rubric, **compute_metrics(examples)}
            for (model, rubric), examples in sorted(groups.items())
        ],
    }
