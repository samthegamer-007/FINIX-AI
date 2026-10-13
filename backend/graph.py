"""LangGraph hub-and-spoke: every spoke returns to Finix's router; spokes never talk to each other."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents import dimon, finix, frank, kova, mike, rome


class FinixState(TypedDict, total=False):
    # input
    user_id: str
    chat_id: str
    user_text: str
    history: list
    attachments: list
    ref_charts: list
    # Frank
    memory_ctx: str
    holdings: list
    # Finix
    plan: dict
    steps: list
    done: list
    next: str
    final_text: str
    # spokes
    rome: dict
    kova_results: list
    kova_series: dict
    kova_tables: dict
    kova_errors: list
    dimon: dict
    charts: list
    chart_pngs: list
    files: list


SPOKES = ["rome", "kova", "dimon", "mike_charts", "compose", "mike_export"]


def build():
    g = StateGraph(FinixState)
    g.add_node("frank_recall", frank.recall)
    g.add_node("finix_plan", finix.plan_node)
    g.add_node("router", finix.router_node)
    g.add_node("rome", rome.run)
    g.add_node("kova", kova.run)
    g.add_node("dimon", dimon.run)
    g.add_node("mike_charts", mike.charts)
    g.add_node("compose", finix.compose_node)
    g.add_node("mike_export", mike.export)
    g.add_node("frank_store", frank.store)

    g.add_edge(START, "frank_recall")
    g.add_edge("frank_recall", "finix_plan")
    g.add_edge("finix_plan", "router")
    g.add_conditional_edges("router", lambda s: s["next"], {n: n for n in SPOKES + ["frank_store"]})
    for n in SPOKES:
        g.add_edge(n, "router")
    g.add_edge("frank_store", END)
    return g.compile()


_compiled = None


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build()
    return _compiled
