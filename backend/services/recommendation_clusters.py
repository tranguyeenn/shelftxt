from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from uuid import UUID
import re

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.metadata_specificity import is_generic_metadata, metadata_specificity, normalize_specificity_term
from backend.services.recommendation import (
    MAX_RECOMMENDATION_BOOKS,
    _candidate_status,
    _normalize_style,
    books_to_dataframe,
    get_books_for_recommendation,
    recommendation_sections_response,
)
from backend.services.recommendation_builder import build_recommendations
from backend.services.recommendation_discovery import discovery_candidate_rows
from backend.services.recommendation_feedback import (
    active_feedback_for_user,
    active_not_interested_identities,
    feedback_to_ranking_records,
)

MAX_ANCHORS_PER_CLUSTER = 3
DEFAULT_RECOMMENDATIONS_PER_CLUSTER = 3

CLUSTER_IDENTITY_TERMS: dict[str, tuple[str, ...]] = {
    "literary-classics": ("Russian realism", "psychological classics", "moral conflict", "literary relationships"),
    "ya-dystopian-speculative": ("survival competitions", "dystopian rebellion", "state control", "resistance"),
    "ya-mystery-thriller": ("criminal profilers", "serial investigations", "teen detectives", "cold cases"),
    "contemporary-romance-new-adult": ("women in STEM", "academic rivals", "romantic comedy", "contemporary relationships"),
    "fantasy": ("found family", "magic", "fae courts", "fantasy quests"),
}

GENERIC_HEADER_TERMS = {
    "young adult",
    "children's fiction",
    "childrens fiction",
    "juvenile fiction",
    "new york times bestseller",
    "schools",
    "school",
    "fiction",
    "literature",
    "general",
    "romance",
    "fantasy",
    "contemporary",
}


@dataclass(frozen=True)
class ClusterRule:
    cluster_id: str
    label: str
    title: str
    keywords: tuple[str, ...]
    authors: tuple[str, ...] = ()
    title_keywords: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()


CLUSTER_RULES = (
    ClusterRule(
        cluster_id="literary-classics",
        label="Literary Classics",
        title="Because you enjoyed Literary Classics",
        keywords=(
            "classic",
            "classics",
            "literary",
            "literature",
            "russian literature",
            "historical fiction",
            "drama",
            "tragedy",
        ),
        authors=("tolstoy", "shakespeare", "fitzgerald", "dickens", "hawthorne", "eliot", "austen"),
        title_keywords=("anna karenina", "war and peace", "great gatsby", "ivan ilyich"),
    ),
    ClusterRule(
        cluster_id="ya-dystopian-speculative",
        label="YA Dystopian / Speculative",
        title="Because you enjoyed The Hunger Games",
        keywords=(
            "dystopian",
            "dystopia",
            "science fiction",
            "speculative",
            "rebellion",
            "post-apocalyptic",
        ),
        title_keywords=("hunger games", "catching fire", "mockingjay", "scythe"),
        required_any=("dystopian", "dystopia", "speculative", "rebellion", "post-apocalyptic", "hunger games", "maze runner", "scythe"),
    ),
    ClusterRule(
        cluster_id="ya-mystery-thriller",
        label="YA Mystery / Thriller",
        title="Because you enjoyed The Naturals",
        keywords=(
            "mystery",
            "thriller",
            "crime fiction",
            "detective",
            "serial killer",
            "profiling",
            "psychological",
            "suspense",
            "puzzle",
        ),
        authors=("jennifer lynn barnes", "maureen johnson"),
        title_keywords=("naturals", "killer instinct", "all in", "bad blood", "truly devious"),
        required_any=("mystery", "thriller", "crime fiction", "detective", "serial killer", "profiling", "suspense", "puzzle", "naturals", "truly devious"),
    ),
    ClusterRule(
        cluster_id="contemporary-romance-new-adult",
        label="Contemporary Romance / New Adult",
        title="Because you enjoyed Book Lovers",
        keywords=(
            "romance",
            "contemporary romance",
            "new adult",
            "love stories",
            "relationships",
            "romantic comedy",
        ),
        authors=("emily henry", "ali hazelwood", "abby jimenez", "tessa bailey"),
        title_keywords=("book lovers", "happy place", "funny story", "beach read", "deep end"),
        required_any=("contemporary romance", "new adult", "romantic comedy", "book lovers", "happy place", "funny story", "deep end", "emily henry", "ali hazelwood"),
        excluded_keywords=("fantasy fiction", "high fantasy", "paranormal"),
    ),
    ClusterRule(
        cluster_id="fantasy",
        label="Fantasy",
        title="Because you enjoyed Fantasy",
        keywords=("fantasy", "magic", "paranormal", "faeries", "juvenile fantasy"),
        title_keywords=("court of", "amari"),
        required_any=("fantasy", "magic", "paranormal", "faeries", "court of", "amari"),
    ),
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "cluster"


def _list_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _row_title(row) -> str:
    return _text(row.get("Title") or row.get("title"))


def _row_author(row) -> str:
    return _text(row.get("Authors") or row.get("author"))


def _row_tags(row) -> list[str]:
    return [*_list_values(row.get("Genres")), *_list_values(row.get("Subjects"))]


def _row_identity(row) -> str:
    for key in (
        "External Work ID",
        "Work Key",
        "External ID",
        "External ISBN",
        "ISBN/UID",
        "Book ID",
    ):
        value = _text(row.get(key))
        if value:
            return f"{key}:{value.casefold()}"
    title = _row_title(row).casefold()
    author = _row_author(row).casefold()
    return f"title:{title}|author:{author}"


def _row_rating(row) -> float:
    try:
        return float(row.get("Star Rating") or 0)
    except (TypeError, ValueError):
        return 0.0


def _rule_score(row, rule: ClusterRule) -> int:
    haystack = " ".join(
        [
            _row_title(row),
            _row_author(row),
            *_row_tags(row),
        ]
    ).casefold()
    if rule.excluded_keywords and any(keyword in haystack for keyword in rule.excluded_keywords):
        return 0
    if rule.required_any and not any(keyword in haystack for keyword in rule.required_any):
        return 0
    score = 0
    score += sum(2 for keyword in rule.keywords if keyword in haystack)
    score += sum(3 for author in rule.authors if author in haystack)
    score += sum(4 for title in rule.title_keywords if title in haystack)
    return score


def _best_rule(row) -> ClusterRule | None:
    scored = sorted(((_rule_score(row, rule), rule) for rule in CLUSTER_RULES), key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return None


def _fallback_rule(row) -> ClusterRule:
    label = next((tag for tag in _row_tags(row) if tag), "General Reading")
    title_label = label[:1].upper() + label[1:]
    return ClusterRule(
        cluster_id=f"topic-{_slug(label)}",
        label=title_label,
        title=f"Because you enjoyed {title_label}",
        keywords=(label.casefold(),),
    )


def _is_anchor_candidate(row) -> bool:
    status = _candidate_status(row)
    if status != "completed":
        return False
    return _row_rating(row) >= 4.0 or bool(_best_rule(row))


def _anchor_payload(row) -> dict:
    return {
        "title": _row_title(row),
        "author": _row_author(row),
        "rating": _row_rating(row) or None,
        "book_id": str(row.get("Book ID")) if row.get("Book ID") is not None else None,
        "work_id": _text(row.get("Work Key") or row.get("External Work ID")) or None,
        "genres": _list_values(row.get("Genres")),
        "subjects": _list_values(row.get("Subjects")),
    }


def _append_discovery(base_df: pd.DataFrame, discovery_rows: list[dict]) -> pd.DataFrame:
    df = base_df.copy()
    if not discovery_rows:
        return df.astype(object).where(pd.notnull(df), None) if not df.empty else df
    discovery_df = pd.DataFrame(discovery_rows)
    for column in discovery_df.columns:
        if column not in df.columns:
            df[column] = None
    for column in df.columns:
        if column not in discovery_df.columns:
            discovery_df[column] = None
    df = pd.DataFrame([*df.to_dict("records"), *discovery_df[df.columns].to_dict("records")])
    return df.astype(object).where(pd.notnull(df), None) if not df.empty else df


def _dominant_terms(rows: list[pd.Series], *, limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    seen_display: dict[str, str] = {}
    for row in rows:
        for tag in _row_tags(row):
            key = tag.casefold()
            if not key:
                continue
            normalized = normalize_specificity_term(tag)
            if normalized in GENERIC_HEADER_TERMS or is_generic_metadata(normalized):
                continue
            specificity = metadata_specificity(tag)
            if specificity < 0.5:
                continue
            counts[key] += max(1, round(specificity * 3))
            seen_display.setdefault(key, tag)
    return [seen_display[key] for key, _count in counts.most_common(limit)]


def _cluster_identity_terms(cluster_id: str, rows: list[pd.Series], *, limit: int = 5) -> list[str]:
    terms = list(CLUSTER_IDENTITY_TERMS.get(cluster_id, ()))
    terms.extend(_dominant_terms(rows, limit=limit * 2))
    seen: set[str] = set()
    filtered: list[str] = []
    for term in terms:
        key = normalize_specificity_term(term)
        if not key or key in seen:
            continue
        if key in GENERIC_HEADER_TERMS or is_generic_metadata(key):
            continue
        if metadata_specificity(term) < 0.5 and term not in CLUSTER_IDENTITY_TERMS.get(cluster_id, ()):
            continue
        seen.add(key)
        filtered.append(term)
        if len(filtered) >= limit:
            break
    return filtered


def _candidate_matches_cluster(row, rule: ClusterRule, anchor_terms: set[str], anchor_authors: set[str]) -> bool:
    if _rule_score(row, rule) > 0:
        return True
    if not rule.cluster_id.startswith("topic-"):
        author = _row_author(row).casefold()
        return bool(author and author in anchor_authors and rule.authors and author in rule.authors)
    row_terms = {tag.casefold() for tag in _row_tags(row)}
    if row_terms.intersection(anchor_terms):
        return True
    author = _row_author(row).casefold()
    return bool(author and author in anchor_authors)


def _cluster_dataframe(df: pd.DataFrame, anchor_rows: list[pd.Series], rule: ClusterRule) -> pd.DataFrame:
    anchor_ids = {_row_identity(row) for row in anchor_rows}
    anchor_terms = {tag.casefold() for row in anchor_rows for tag in _row_tags(row)}
    anchor_authors = {_row_author(row).casefold() for row in anchor_rows if _row_author(row)}
    selected: list[dict] = []
    seen: set[str] = set()

    for _, row in df.iterrows():
        identity = _row_identity(row)
        if identity in seen:
            continue
        status = _candidate_status(row)
        include = identity in anchor_ids or (
            status == "not_started" and _candidate_matches_cluster(row, rule, anchor_terms, anchor_authors)
        )
        if not include:
            continue
        seen.add(identity)
        selected.append(row.to_dict())

    return pd.DataFrame(selected, columns=df.columns).astype(object).where(pd.notnull(pd.DataFrame(selected, columns=df.columns)), None) if selected else pd.DataFrame(columns=df.columns)


def _unique_recommendations(items: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for item in items:
        book = item.get("recommended_book") or item.get("book") or {}
        identity = _text(
            item.get("recommendation_id")
            or item.get("work_id")
            or book.get("recommendation_id")
            or book.get("work_id")
            or item.get("isbn")
            or book.get("isbn")
            or item.get("title")
        ).casefold()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
    return unique


def flatten_clustered_recommendations(
    clusters: list[dict],
    *,
    top_n: int = 10,
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
) -> list[dict]:
    queues = [
        (
            cluster["cluster_id"],
            deque(cluster.get("recommendations", [])[:max_per_cluster]),
        )
        for cluster in clusters
        if cluster.get("recommendations")
    ]
    flattened: list[dict] = []
    seen: set[str] = set()
    while queues and len(flattened) < top_n:
        next_queues = []
        for cluster_id, queue in queues:
            while queue:
                item = queue.popleft()
                identity = _text(item.get("recommendation_id") or item.get("work_id") or item.get("title")).casefold()
                if identity in seen:
                    continue
                enriched = {**item, "taste_cluster_id": cluster_id}
                flattened.append(enriched)
                seen.add(identity)
                break
            if queue:
                next_queues.append((cluster_id, queue))
            if len(flattened) >= top_n:
                break
        queues = next_queues
    return flattened


def build_reading_clusters_from_dataframe(
    df: pd.DataFrame,
    *,
    top_n: int = 3,
    style: str = "balanced",
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
    feedback_records: list[dict] | None = None,
    excluded_identities: set[str] | None = None,
) -> list[dict]:
    if df.empty:
        return []

    grouped: defaultdict[str, list[pd.Series]] = defaultdict(list)
    rules_by_id: dict[str, ClusterRule] = {}
    for _, row in df.iterrows():
        if not _is_anchor_candidate(row):
            continue
        rule = _best_rule(row) or _fallback_rule(row)
        grouped[rule.cluster_id].append(row)
        rules_by_id[rule.cluster_id] = rule

    clusters: list[dict] = []
    normalized_style = _normalize_style(style)
    for cluster_id, rows in grouped.items():
        rule = rules_by_id[cluster_id]
        if cluster_id == "topic-general-reading":
            continue
        if cluster_id.startswith("topic-") and len(rows) < 2:
            continue
        anchors = sorted(
            rows,
            key=lambda row: (-_rule_score(row, rule), -_row_rating(row), _row_title(row).casefold()),
        )[:MAX_ANCHORS_PER_CLUSTER]
        cluster_df = _cluster_dataframe(df, anchors, rule)
        recommendations = build_recommendations(
            cluster_df,
            top_n=max(top_n, max_per_cluster),
            style=normalized_style,
            feedback_records=feedback_records,
            excluded_identities=excluded_identities,
        )
        recommendations = _unique_recommendations(recommendations)[:max_per_cluster]
        if not recommendations:
            continue
        terms = _cluster_identity_terms(cluster_id, rows)
        title = _cluster_title(rule, anchors)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "title": title,
                "reading_identity": title,
                "why": (
                    f"Clustered from {len(rows)} completed or highly rated books"
                    + (f" around {', '.join(terms[:3])}." if terms else ".")
                ),
                "anchors": [_anchor_payload(row) for row in anchors],
                "dominant_genres": terms,
                "dominant_themes": terms,
                "cluster_size": len(rows),
                "recommendations": recommendation_sections_response(recommendations, style=normalized_style)["sections"][0]["items"]
                if recommendations
                else [],
            }
        )

    clusters.sort(
        key=lambda cluster: (
            -cluster["cluster_size"],
            -max((float(item.get("score") or 0.0) for item in cluster["recommendations"]), default=0.0),
            cluster["title"].casefold(),
        )
    )
    return clusters


def _cluster_title(rule: ClusterRule, anchors: list[pd.Series]) -> str:
    anchor_titles = {_row_title(row).casefold() for row in anchors}
    if rule.cluster_id == "ya-dystopian-speculative" and "the hunger games" in anchor_titles:
        return "Survival competitions and dystopian rebellion"
    if rule.cluster_id == "ya-mystery-thriller" and "the naturals" in anchor_titles:
        return "Criminal profilers and teen mysteries"
    if rule.cluster_id == "contemporary-romance-new-adult" and "book lovers" in anchor_titles:
        return "Contemporary romance and academic rivals"
    if rule.cluster_id == "literary-classics":
        return "Literary relationships and moral conflict"
    if rule.cluster_id == "fantasy":
        return "Magic, quests, and found family"
    identity_terms = CLUSTER_IDENTITY_TERMS.get(rule.cluster_id)
    if identity_terms:
        label = " and ".join(identity_terms[:2])
        return label[:1].upper() + label[1:]
    return rule.label


def get_clustered_recommendations(
    db: Session,
    user_id: UUID,
    *,
    top_n: int = 3,
    style: str = "balanced",
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
    include_discovery: bool = True,
) -> list[dict]:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    base_df = books_to_dataframe(books, user_id)
    discovery_rows: list[dict] = []
    if include_discovery:
        discovery_rows, _diagnostics = discovery_candidate_rows(
            db,
            user_id,
            books,
            limit=max(50, top_n * max_per_cluster * 5),
            allow_external=True,
        )
    df = _append_discovery(base_df, discovery_rows)
    active_feedback = active_feedback_for_user(db, user_id)
    return build_reading_clusters_from_dataframe(
        df,
        top_n=top_n,
        style=style,
        max_per_cluster=max_per_cluster,
        feedback_records=feedback_to_ranking_records(active_feedback),
        excluded_identities=active_not_interested_identities(db, user_id),
    )
