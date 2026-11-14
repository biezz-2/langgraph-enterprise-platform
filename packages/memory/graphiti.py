import os
import time
import socket
import logging
import asyncio
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union, Set
from pydantic import BaseModel, Field

# Matikan telemetry/PostHog agar latency minimal dan tidak blocking
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

from packages.core.db import get_db_connection

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("lgp.memory.graphiti")

def resolve_router_base_url() -> str:
    """Deteksi local IPv4 reverse proxy (20128) atau fallback ke domain HTTPS publik."""
    env_url = os.environ.get("ROUTER_BASE_URL") or os.environ.get("NINE_ROUTER_BASE_URL")
    if env_url:
        return env_url
    try:
        with socket.create_connection(("127.0.0.1", 20128), timeout=0.3):
            return "http://127.0.0.1:20128/v1"
    except Exception:
        return "https://9router.biezz.my.id/v1"

# Check availability of graphiti-core & falkordb
try:
    from falkordb import FalkorDB
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.cross_encoder.client import CrossEncoderClient
    GRAPHITI_AVAILABLE = True
except ImportError as e:
    GRAPHITI_AVAILABLE = False
    FalkorDB = None
    Graphiti = None
    FalkorDriver = None
    OpenAIGenericClient = None
    LLMConfig = None
    OpenAIEmbedder = object
    OpenAIEmbedderConfig = None
    CrossEncoderClient = object
    logger.warning("graphiti-core or falkordb not installed; will use SQLite fallback: %s", e)


class MemoryTaxonomy:
    """Ontologi dan taksonomi memori subagent LGP v2.0."""
    CATEGORIES = [
        "episodic",    # Log kejadian, run_id, percakapan, jejak runtime
        "semantic",    # Fakta bisnis, kebijakan platform, referensi entitas
        "procedural",  # SOP subagent, prompt chains, tool bindings
        "working",     # State aktif di checkpoint (scratchpad, draft)
        "meta"         # Audit log, konsensus, evaluasi performa, metrik
    ]

    CATEGORY_COLORS = {
        "episodic": "#3b82f6",    # Blue
        "semantic": "#10b981",    # Emerald
        "procedural": "#f59e0b",  # Amber
        "working": "#8b5cf6",     # Violet
        "meta": "#64748b"         # Slate
    }


# ============================================================================
# RDF/OWL Standard Edge Types (per W3C recommendations)
# ============================================================================
class RDFEdgeTypes:
    """Tipe edge standar RDF/OWL untuk knowledge graph interoperability."""
    RDF_TYPE = "rdf:type"
    RDFS_SUBCLASS_OF = "rdfs:subClassOf"
    RDFS_LABEL = "rdfs:label"
    RDFS_COMMENT = "rdfs:comment"
    OWL_OBJECT_PROPERTY = "owl:ObjectProperty"
    OWL_DATATYPE_PROPERTY = "owl:DatatypeProperty"
    OWL_EQUIVALENT_CLASS = "owl:equivalentClass"
    OWL_EQUIVALENT_PROPERTY = "owl:equivalentProperty"
    OWL_DISJOINT_WITH = "owl:disjointWith"
    OWL_INVERSE_OF = "owl:inverseOf"
    OWL_SAME_AS = "owl:sameAs"
    PROV_WAS_GENERATED_BY = "prov:wasGeneratedBy"
    PROV_WAS_DERIVED_FROM = "prov:wasDerivedFrom"
    PROV_WAS_ATTRIBUTED_TO = "prov:wasAttributedTo"
    DCTERMS_IS_PART_OF = "dcterms:isPartOf"
    DCTERMS_HAS_PART = "dcterms:hasPart"
    DCTERMS_CREATOR = "dcterms:creator"
    DCTERMS_CREATED = "dcterms:created"
    DCTERMS_MODIFIED = "dcterms:modified"
    SKOS_BROADER = "skos:broader"
    SKOS_NARROWER = "skos:narrower"
    SKOS_RELATED = "skos:related"
    SKOS_PREFLABEL = "skos:prefLabel"
    SKOS_ALTLABEL = "skos:altLabel"

    # Custom domain-specific (prefixed to avoid collision)
    LGP_HAS_CAPABILITY = "lgp:hasCapability"
    LGP_EXECUTED = "lgp:executed"
    LGP_GENERATED_FACT = "lgp:generatedFact"
    LGP_HAS_FACT = "lgp:hasFact"
    LGP_RELATES_TO = "lgp:relatesTo"
    LGP_REPRESENTATION = "lgp:representation"
    LGP_PART_OF = "lgp:partOf"
    LGP_NPMI_CORRELATION = "lgp:npmicorrelation"
    LGP_IS_EPISODE = "lgp:isEpisode"

    @classmethod
    def all(cls) -> List[str]:
        return [v for k, v in cls.__dict__.items() if not k.startswith("_") and isinstance(v, str)]


# ============================================================================
# WebVOWL / Chowlk Visual Notation Shape Mapping
# ============================================================================
class VisualNotation:
    """Mapping tipe node/edge ke visual notation standar WebVOWL/Chowlk."""
    
    # Node shapes per WebVOWL 2.0 specification
    NODE_SHAPES = {
        # OWL Classes → ellipse (circle)
        "category": "ellipse",
        "subagent": "ellipse", 
        "entity": "ellipse",
        # Instances → rectangle
        "episode": "rectangle",
        "instance": "rectangle",
        # Fact entities (data-like) → rounded rectangle (WebVOWL datatype/literal style)
        "fact_entity": "roundrectangle",
        # Datatypes → rounded rectangle
        "datatype": "roundrectangle",
        "literal": "roundrectangle",
    }
    
    # Edge types per WebVOWL
    EDGE_TYPES = {
        RDFEdgeTypes.RDFS_SUBCLASS_OF: {"style": "solid", "arrow": "triangle", "label": "subClassOf"},
        RDFEdgeTypes.OWL_OBJECT_PROPERTY: {"style": "solid", "arrow": "triangle", "label": ""},
        RDFEdgeTypes.OWL_DATATYPE_PROPERTY: {"style": "dashed", "arrow": "triangle", "label": ""},
        RDFEdgeTypes.OWL_EQUIVALENT_CLASS: {"style": "dotted", "arrow": "triangle", "label": "≡"},
        RDFEdgeTypes.OWL_SAME_AS: {"style": "dotted", "arrow": "diamond", "label": "sameAs"},
        RDFEdgeTypes.PROV_WAS_GENERATED_BY: {"style": "solid", "arrow": "vee", "label": "generatedBy"},
        RDFEdgeTypes.DCTERMS_IS_PART_OF: {"style": "solid", "arrow": "triangle", "label": "partOf"},
        RDFEdgeTypes.SKOS_BROADER: {"style": "solid", "arrow": "triangle", "label": "broader"},
        RDFEdgeTypes.SKOS_NARROWER: {"style": "solid", "arrow": "triangle", "label": "narrower"},
        RDFEdgeTypes.SKOS_RELATED: {"style": "dashed", "arrow": "none", "label": "related"},
        # LGP custom
        RDFEdgeTypes.LGP_HAS_CAPABILITY: {"style": "solid", "arrow": "triangle", "label": "hasCapability"},
        RDFEdgeTypes.LGP_EXECUTED: {"style": "solid", "arrow": "vee", "label": "executed"},
        RDFEdgeTypes.LGP_GENERATED_FACT: {"style": "solid", "arrow": "vee", "label": "generatedFact"},
        RDFEdgeTypes.LGP_HAS_FACT: {"style": "solid", "arrow": "triangle", "label": "hasFact"},
        RDFEdgeTypes.LGP_RELATES_TO: {"style": "dashed", "arrow": "none", "label": "relatesTo"},
        RDFEdgeTypes.LGP_REPRESENTATION: {"style": "dotted", "arrow": "triangle", "label": "represents"},
        RDFEdgeTypes.LGP_PART_OF: {"style": "solid", "arrow": "triangle", "label": "partOf"},
        RDFEdgeTypes.LGP_NPMI_CORRELATION: {"style": "dashed", "arrow": "none", "label": "npmicorr"},
        RDFEdgeTypes.LGP_IS_EPISODE: {"style": "solid", "arrow": "triangle", "label": "isEpisode"},
    }
    
    # Category to CSS design token mapping (replaces hardcoded hex)
    CATEGORY_TOKENS = {
        "episodic": "var(--color-episodic, #3b82f6)",
        "semantic": "var(--color-semantic, #10b981)",
        "procedural": "var(--color-procedural, #f59e0b)",
        "working": "var(--color-working, #8b5cf6)",
        "meta": "var(--color-meta, #64748b)",
        "subagent": "var(--color-subagent, #0ea5e9)",
        "episode_completed": "var(--color-episode-completed, #38bdf8)",
        "episode_failed": "var(--color-episode-failed, #ef4444)",
        "episode_running": "var(--color-episode-running, #fbbf24)",
        "fact_active": "var(--color-fact-active, #10b981)",
        "fact_invalid": "var(--color-fact-invalid, #f43f5e)",
        "falkor_entity": "var(--color-falkor-entity, #a855f7)",
        "correlation_positive": "var(--color-corr-positive, #34d399)",
        "correlation_negative": "var(--color-corr-negative, #f43f5e)",
        "correlation_neutral": "var(--color-corr-neutral, #64748b)",
    }

    # Okabe-Ito CVD-safe color palette (color-vision-deficiency safe)
    CVD_PALETTE = [
        "#000000",  # Black
        "#E69F00",  # Orange
        "#56B4E9",  # Sky Blue
        "#009E73",  # Bluish Green
        "#F0E442",  # Yellow
        "#0072B2",  # Blue
        "#D55E00",  # Vermillion
        "#CC79A7",  # Reddish Purple
    ]

    # CSS Design Tokens mapping (OPDA ADR-0043 compliant)
    # These map to CSS custom properties defined in the application's DESIGN.md / global stylesheet
    DESIGN_TOKENS = {
        # Semantic colors
        "--color-semantic": "#10b981",
        "--color-episodic": "#3b82f6",
        "--color-procedural": "#f59e0b",
        "--color-working": "#8b5cf6",
        "--color-meta": "#64748b",
        "--color-subagent": "#0ea5e9",
        # Episode status colors
        "--color-episode-completed": "#38bdf8",
        "--color-episode-failed": "#ef4444",
        "--color-episode-running": "#fbbf24",
        # Fact status colors
        "--color-fact-active": "#10b981",
        "--color-fact-invalid": "#f43f5e",
        "--color-falkor-entity": "#a855f7",
        # Correlation colors
        "--color-corr-positive": "#34d399",
        "--color-corr-negative": "#f43f5e",
        "--color-corr-neutral": "#64748b",
        # UI base colors
        "--color-text-primary": "#1e293b",
        "--color-text-outline": "#ffffff",
        "--color-border": "#e2e8f0",
        "--color-selection-border": "#3b82f6",
        "--color-selection-box": "#3b82f6",
        "--color-highlight": "#f59e0b",
        "--color-edge-label-bg": "#ffffff",
        "--color-active-bg": "transparent",
        # Typography
        "--font-family": "Inter, system-ui, sans-serif",
        # Motion (respects prefers-reduced-motion)
        "--animation-duration": "200ms",
        "--animation-easing": "ease-out",
    }


# ============================================================================
# Cytoscape.js Stylesheet Generator
# ============================================================================
class CytoscapeStylesheet:
    """
    Generator Cytoscape.js stylesheet JSON untuk knowledge graph visualization.
    Memisahkan visual encoding dari data (standar Cytoscape.js + OPDA ADR-0043).
    """
    
    def __init__(self, theme: str = "light"):
        self.theme = theme
        self._token_prefix = "--color"
    
    def generate(self) -> List[Dict[str, Any]]:
        """Generate full stylesheet array per Cytoscape.js JSON spec."""
        return [
            # Core canvas
            {
                "selector": "core",
                "style": {
                    "selection-box-color": "var(--color-selection-box, #3b82f6)",
                    "selection-box-opacity": 0.15,
                    "selection-box-border-color": "var(--color-selection-border, #3b82f6)",
                    "active-bg-color": "var(--color-active-bg, transparent)",
                    "active-bg-opacity": 0,
                    "active-bg-size": 0,
                }
            },
            # Base node styles
            {
                "selector": "node",
                "style": {
                    "label": "data(label)",
                    "font-size": "mapData(size, 10, 30, 8, 14)",
                    "font-family": "var(--font-family, 'Inter, system-ui, sans-serif')",
                    "color": "var(--color-text-primary, #1e293b)",
                    "text-valign": "center",
                    "text-halign": "center",
                    "text-outline-width": 2,
                    "text-outline-color": "var(--color-text-outline, #ffffff)",
                    "text-wrap": "wrap",
                    "text-max-width": 100,
                    "background-color": "data(color)",
                    "border-width": "mapData(charge, 0.5, 1.5, 1, 3)",
                    "border-color": "var(--color-border, #e2e8f0)",
                    "shape": "data(vowl_shape)",
                    "width": "mapData(size, 10, 30, 20, 60)",
                    "height": "mapData(size, 10, 30, 20, 60)",
                    "overlay-padding": 6,
                    "z-index": 10,
                    "transition-property": "background-color, border-color, width, height, opacity",
                    "transition-duration": "200ms",
                }
            },
            # Node states
            {
                "selector": "node:selected",
                "style": {
                    "border-width": 4,
                    "border-color": "var(--color-selection-border, #3b82f6)",
                    "overlay-padding": 8,
                    "z-index": 100,
                }
            },
            {
                "selector": "node.highlighted",
                "style": {
                    "border-width": 3,
                    "border-color": "var(--color-highlight, #f59e0b)",
                    "z-index": 50,
                }
            },
            {
                "selector": "node.faded",
                "style": {
                    "opacity": 0.25,
                    "text-opacity": 0.25,
                }
            },
            # Category-specific node styles (data-driven)
            {
                "selector": "node[category=\"episodic\"]",
                "style": {
                    "background-color": "var(--color-episodic, #3b82f6)",
                }
            },
            {
                "selector": "node[category=\"semantic\"]",
                "style": {
                    "background-color": "var(--color-semantic, #10b981)",
                }
            },
            {
                "selector": "node[category=\"procedural\"]",
                "style": {
                    "background-color": "var(--color-procedural, #f59e0b)",
                }
            },
            {
                "selector": "node[category=\"working\"]",
                "style": {
                    "background-color": "var(--color-working, #8b5cf6)",
                }
            },
            {
                "selector": "node[category=\"meta\"]",
                "style": {
                    "background-color": "var(--color-meta, #64748b)",
                }
            },
            # Status-based styles
            {
                "selector": "node[status=\"invalid\"]",
                "style": {
                    "background-color": "var(--color-fact-invalid, #f43f5e)",
                    "border-style": "dashed",
                }
            },
            {
                "selector": "node[status=\"decaying\"]",
                "style": {
                    "opacity": 0.6,
                    "border-style": "dotted",
                }
            },
            # Base edge styles
            {
                "selector": "edge",
                "style": {
                    "label": "data(relation_label)",
                    "font-size": "mapData(weight, 0.4, 2.0, 7, 11)",
                    "font-family": "var(--font-family, 'Inter, system-ui, sans-serif')",
                    "color": "var(--color-text-primary, #1e293b)",
                    "text-background-color": "var(--color-edge-label-bg, #ffffff)",
                    "text-background-opacity": 0.85,
                    "text-background-padding": 3,
                    "text-background-shape": "roundrectangle",
                    "curve-style": "bezier",
                    "line-color": "data(edge_color)",
                    "line-style": "data(edge_style)",
                    "width": "mapData(weight, 0.4, 2.0, 1, 4)",
                    "target-arrow-shape": "data(edge_arrow)",
                    "target-arrow-color": "data(edge_color)",
                    "arrow-scale": 1.2,
                    "overlay-padding": 4,
                    "z-index": 5,
                    "transition-property": "line-color, width, opacity",
                    "transition-duration": "200ms",
                }
            },
            # Edge states
            {
                "selector": "edge:selected",
                "style": {
                    "width": 5,
                    "line-color": "var(--color-selection-border, #3b82f6)",
                    "target-arrow-color": "var(--color-selection-border, #3b82f6)",
                    "z-index": 100,
                }
            },
            {
                "selector": "edge.highlighted",
                "style": {
                    "width": "mapData(weight, 0.4, 2.0, 3, 6)",
                    "line-color": "var(--color-highlight, #f59e0b)",
                    "target-arrow-color": "var(--color-highlight, #f59e0b)",
                    "z-index": 50,
                }
            },
            {
                "selector": "edge.faded",
                "style": {
                    "opacity": 0.15,
                    "text-opacity": 0.15,
                }
            },
            # Edge type specific styles (data-driven via edge_type)
            {
                "selector": "edge[edge_type=\"rdfs:subClassOf\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"owl:ObjectProperty\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"owl:DatatypeProperty\"]",
                "style": {
                    "line-style": "dashed",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"owl:equivalentClass\"]",
                "style": {
                    "line-style": "dotted",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"owl:sameAs\"]",
                "style": {
                    "line-style": "dotted",
                    "target-arrow-shape": "diamond",
                }
            },
            {
                "selector": "edge[edge_type=\"prov:wasGeneratedBy\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "vee",
                }
            },
            {
                "selector": "edge[edge_type=\"dcterms:isPartOf\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"skos:broader\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"skos:narrower\"]",
                "style": {
                    "line-style": "solid",
                    "target-arrow-shape": "triangle",
                }
            },
            {
                "selector": "edge[edge_type=\"skos:related\"]",
                "style": {
                    "line-style": "dashed",
                    "target-arrow-shape": "none",
                }
            },
            # LGP custom edge types
            {
                "selector": "edge[edge_type^=\"lgp:\"]",
                "style": {
                    "line-style": "data(edge_style)",
                    "target-arrow-shape": "data(edge_arrow)",
                }
            },
            # Animated edges for correlations
            {
                "selector": "edge.animated",
                "style": {
                    "line-style": "dashed",
                    "line-dash-pattern": [8, 4],
                    "animation": "dash 1s linear infinite",
                }
            },
        ]
    
    def to_json(self, indent: int = 2) -> str:
        """Export stylesheet as JSON string."""
        return json.dumps(self.generate(), indent=indent)
    
    def save(self, path: str) -> None:
        """Save stylesheet to file."""
        with open(path, "w") as f:
            f.write(self.to_json())


# ============================================================================
# Graph Export Utilities (DOT, GraphML, Cytoscape JSON)
# ============================================================================
class GraphExporter:
    """Export neuron graph ke format standar: DOT, GraphML, Cytoscape JSON."""
    
    def __init__(self, graph_data: Dict[str, Any]):
        self.graph_data = graph_data
        self.nodes = graph_data.get("nodes", [])
        self.edges = graph_data.get("edges", [])
    
    def _node_id(self, node: Dict[str, Any]) -> str:
        return node.get("id", "")
    
    def _sanitize_label(self, label: str) -> str:
        """Escape label for DOT format."""
        return label.replace('"', '\\"').replace("\n", "\\n")
    
    def to_dot(self, rankdir: str = "LR", compound: bool = True) -> str:
        """Export ke GraphViz DOT format dengan subgraph clustering per kategori."""
        lines = [
            f'digraph "MiroFish Neuron Graph" {{',
            f'  rankdir={rankdir};',
            f'  compound={str(compound).lower()};',
            f'  node [fontname="Inter", fontsize=10];',
            f'  edge [fontname="Inter", fontsize=8];',
            f'  bgcolor="transparent";',
            "",
        ]
        
        # Group nodes by category for subgraph clustering
        categories: Dict[str, List[Dict[str, Any]]] = {}
        for node in self.nodes:
            cat = node.get("category", "unknown")
            categories.setdefault(cat, []).append(node)
        
        # Write subgraphs (clusters) per category
        for cat, cat_nodes in categories.items():
            token = VisualNotation.CATEGORY_TOKENS.get(cat, "#64748b")
            # Extract hex fallback from CSS var
            hex_fallback = token.split(",")[-1].strip().rstrip(")") if "," in token else token
            lines.append(f'  subgraph "cluster_{cat}" {{')
            lines.append(f'    label = "{cat.upper()}";')
            lines.append(f'    style = "rounded,dashed";')
            lines.append(f'    color = "{hex_fallback}";')
            lines.append(f'    fontcolor = "{hex_fallback}";')
            for node in cat_nodes:
                node_id = self._node_id(node)
                label = self._sanitize_label(node.get("label", node_id))
                shape = node.get("vowl_shape", VisualNotation.NODE_SHAPES.get(node.get("type", ""), "ellipse"))
                size = node.get("size", 14)
                color = node.get("color", hex_fallback)
                charge = node.get("charge", 1.0)
                lines.append(
                    f'    "{node_id}" ['
                    f'label="{label}", '
                    f'shape={shape}, '
                    f'width={size/14:.2f}, '
                    f'height={size/14:.2f}, '
                    f'fillcolor="{color}", '
                    f'style="filled,rounded", '
                    f'fontcolor="var(--color-text-primary, #1e293b)", '
                    f'penwidth={max(1, charge*2):.1f}'
                    f'];'
                )
            lines.append("  }")
            lines.append("")
        
        # Write edges
        for edge in self.edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if not src or not tgt:
                continue
            relation = edge.get("relation", "")
            edge_type = edge.get("edge_type", relation)
            weight = edge.get("weight", 1.0)
            edge_color = edge.get("color", "#64748b")
            edge_style = VisualNotation.EDGE_TYPES.get(edge_type, {}).get("style", "solid")
            edge_arrow = VisualNotation.EDGE_TYPES.get(edge_type, {}).get("arrow", "vee")
            
            lines.append(
                f'  "{src}" -> "{tgt}" ['
                f'label="{self._sanitize_label(relation)}", '
                f'penwidth={max(0.5, weight*2):.1f}, '
                f'color="{edge_color}", '
                f'style="{edge_style}", '
                f'arrowhead="{edge_arrow}", '
                f'fontcolor="var(--color-text-primary, #1e293b)"'
                f'];'
            )
        
        lines.append("}")
        return "\n".join(lines)
    
    def to_graphml(self) -> str:
        """Export ke GraphML format untuk Gephi/yEd/Cytoscape interoperability."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
            '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns',
            '         http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
            '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
            '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
            '  <key id="category" for="node" attr.name="category" attr.type="string"/>',
            '  <key id="size" for="node" attr.name="size" attr.type="double"/>',
            '  <key id="color" for="node" attr.name="color" attr.type="string"/>',
            '  <key id="charge" for="node" attr.name="charge" attr.type="double"/>',
            '  <key id="status" for="node" attr.name="status" attr.type="string"/>',
            '  <key id="vowl_shape" for="node" attr.name="vowl_shape" attr.type="string"/>',
            '  <key id="valid_at" for="node" attr.name="valid_at" attr.type="string"/>',
            '  <key id="invalid_at" for="node" attr.name="invalid_at" attr.type="string"/>',
            '  <key id="description" for="node" attr.name="description" attr.type="string"/>',
            '  <key id="edge_type" for="edge" attr.name="edge_type" attr.type="string"/>',
            '  <key id="relation" for="edge" attr.name="relation" attr.type="string"/>',
            '  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
            '  <key id="color" for="edge" attr.name="color" attr.type="string"/>',
            '  <key id="edge_style" for="edge" attr.name="edge_style" attr.type="string"/>',
            '  <key id="edge_arrow" for="edge" attr.name="edge_arrow" attr.type="string"/>',
            '  <key id="valid_at" for="edge" attr.name="valid_at" attr.type="string"/>',
            '  <key id="invalid_at" for="edge" attr.name="invalid_at" attr.type="string"/>',
            '  <key id="bitemporal" for="edge" attr.name="bitemporal" attr.type="boolean"/>',
            '  <graph id="MiroFishNeuronGraph" edgedefault="directed">',
        ]
        
        for node in self.nodes:
            node_id = self._node_id(node)
            lines.append(f'    <node id="{node_id}">')
            lines.append(f'      <data key="label"><![CDATA[{node.get("label", node_id)}]]></data>')
            lines.append(f'      <data key="type"><![CDATA[{node.get("type", "")}]]></data>')
            lines.append(f'      <data key="category"><![CDATA[{node.get("category", "")}]]></data>')
            lines.append(f'      <data key="size">{node.get("size", 14)}</data>')
            lines.append(f'      <data key="color"><![CDATA[{node.get("color", "")}]]></data>')
            lines.append(f'      <data key="charge">{node.get("charge", 1.0)}</data>')
            lines.append(f'      <data key="status"><![CDATA[{node.get("status", "active")}]]></data>')
            lines.append(f'      <data key="vowl_shape"><![CDATA[{node.get("vowl_shape", VisualNotation.NODE_SHAPES.get(node.get("type", ""), "ellipse"))}]]></data>')
            if node.get("valid_at"):
                lines.append(f'      <data key="valid_at"><![CDATA[{node.get("valid_at")}]]></data>')
            if node.get("invalid_at"):
                lines.append(f'      <data key="invalid_at"><![CDATA[{node.get("invalid_at")}]]></data>')
            if node.get("description"):
                lines.append(f'      <data key="description"><![CDATA[{node.get("description")}]]></data>')
            lines.append("    </node>")
        
        for edge in self.edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if not src or not tgt:
                continue
            edge_id = edge.get("id", f"{src}->{tgt}")
            lines.append(f'    <edge id="{edge_id}" source="{src}" target="{tgt}">')
            lines.append(f'      <data key="edge_type"><![CDATA[{edge.get("edge_type", edge.get("relation", ""))}]]></data>')
            lines.append(f'      <data key="relation"><![CDATA[{edge.get("relation", "")}]]></data>')
            lines.append(f'      <data key="weight">{edge.get("weight", 1.0)}</data>')
            lines.append(f'      <data key="color"><![CDATA[{edge.get("color", "#64748b")}]]></data>')
            edge_type = edge.get("edge_type", edge.get("relation", ""))
            vinfo = VisualNotation.EDGE_TYPES.get(edge_type, {})
            lines.append(f'      <data key="edge_style"><![CDATA[{vinfo.get("style", "solid")}]]></data>')
            lines.append(f'      <data key="edge_arrow"><![CDATA[{vinfo.get("arrow", "vee")}]]></data>')
            if edge.get("valid_at"):
                lines.append(f'      <data key="valid_at"><![CDATA[{edge.get("valid_at")}]]></data>')
            if edge.get("invalid_at"):
                lines.append(f'      <data key="invalid_at"><![CDATA[{edge.get("invalid_at")}]]></data>')
            if edge.get("bitemporal"):
                lines.append(f'      <data key="bitemporal">true</data>')
            lines.append("    </edge>")
        
        lines.extend(["  </graph>", "</graphml>"])
        return "\n".join(lines)
    
    def to_cytoscape_json(self) -> Dict[str, Any]:
        """Export ke Cytoscape.js JSON format (elements + stylesheet)."""
        elements = {"nodes": [], "edges": []}
        
        for node in self.nodes:
            node_id = self._node_id(node)
            shape = node.get("vowl_shape", VisualNotation.NODE_SHAPES.get(node.get("type", ""), "ellipse"))
            elements["nodes"].append({
                "data": {
                    "id": node_id,
                    "label": node.get("label", node_id),
                    "type": node.get("type", ""),
                    "category": node.get("category", ""),
                    "size": node.get("size", 14),
                    "color": node.get("color", "#64748b"),
                    "charge": node.get("charge", 1.0),
                    "status": node.get("status", "active"),
                    "vowl_shape": shape,
                    "valid_at": node.get("valid_at"),
                    "invalid_at": node.get("invalid_at"),
                    "description": node.get("description", ""),
                    **node.get("attributes", {}),
                },
                "classes": f"{node.get('category', '')} {node.get('status', '')}",
            })
        
        for edge in self.edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if not src or not tgt:
                continue
            edge_type = edge.get("edge_type", edge.get("relation", ""))
            vinfo = VisualNotation.EDGE_TYPES.get(edge_type, {})
            edge_data = {
                "id": edge.get("id", f"{src}->{tgt}"),
                "source": src,
                "target": tgt,
                "relation": edge.get("relation", ""),
                "relation_label": edge.get("relation", ""),
                "edge_type": edge_type,
                "weight": edge.get("weight", 1.0),
                "edge_color": edge.get("color", "#64748b"),
                "edge_style": vinfo.get("style", "solid"),
                "edge_arrow": vinfo.get("arrow", "vee"),
                "valid_at": edge.get("valid_at"),
                "invalid_at": edge.get("invalid_at"),
                "bitemporal": edge.get("bitemporal", False),
                "detail": edge.get("detail", ""),
            }
            classes = []
            if edge.get("animated"):
                classes.append("animated")
            elements["edges"].append({
                "data": edge_data,
                "classes": " ".join(classes) if classes else "",
            })
        
        return {
            "elements": elements,
            "stylesheet": CytoscapeStylesheet().generate(),
            "metadata": {
                "engine": self.graph_data.get("engine", "Graphiti"),
                "style": self.graph_data.get("style", "MiroFish Spiking Neuron Architecture"),
                "timestamp": self.graph_data.get("timestamp", time.time()),
                "stats": self.graph_data.get("stats", {}),
            }
        }
    
    def save_all(self, base_path: str) -> Dict[str, str]:
        """Save all export formats to files."""
        outputs = {}
        
        # DOT
        dot_path = f"{base_path}.dot"
        with open(dot_path, "w") as f:
            f.write(self.to_dot())
        outputs["dot"] = dot_path
        
        # GraphML
        graphml_path = f"{base_path}.graphml"
        with open(graphml_path, "w") as f:
            f.write(self.to_graphml())
        outputs["graphml"] = graphml_path
        
        # Cytoscape JSON
        cyto_path = f"{base_path}.cyto.json"
        with open(cyto_path, "w") as f:
            json.dump(self.to_cytoscape_json(), f, indent=2)
        outputs["cytoscape_json"] = cyto_path
        
        # Stylesheet JSON (standalone)
        style_path = f"{base_path}.stylesheet.json"
        CytoscapeStylesheet().save(style_path)
        outputs["stylesheet"] = style_path
        
        return outputs


class BiTemporalEdge(BaseModel):
    """Representasi edge bi-temporal pada knowledge graph memori."""
    source_id: str
    target_id: str
    relation: str
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphitiNeuronNode(BaseModel):
    """Representasi node neuron memori untuk visualisasi kanvas MiroFish."""
    id: str
    label: str
    neuron_type: str = "entity"  # 'category' | 'subagent' | 'entity' | 'episode'
    charge: float = 1.0
    category: str = "semantic"
    status: str = "active"       # 'active' | 'invalid' | 'decaying'
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


if GRAPHITI_AVAILABLE:
    class SimpleCrossEncoder(CrossEncoderClient):
        """Cross-encoder passthrough berbobot konstan untuk konsumsi memori minimal."""
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            return [(p, 1.0) for p in passages]

    class FallbackOpenAIEmbedder(OpenAIEmbedder):
        """Embedder dengan fallback otomatis dari nv-embedqa-e5-v5 ke text-embedding-3-small."""
        def __init__(self, primary_config: OpenAIEmbedderConfig, fallback_config: OpenAIEmbedderConfig):
            super().__init__(primary_config)
            self.fallback_config = fallback_config
            self._using_fallback = False
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=primary_config.api_key, base_url=primary_config.base_url, timeout=12.0, max_retries=1)
            self.fallback_client = AsyncOpenAI(api_key=fallback_config.api_key, base_url=fallback_config.base_url, timeout=12.0, max_retries=1)

        def _activate_fallback(self, reason: Any):
            if not self._using_fallback:
                logger.warning(
                    "Primary embedder '%s' gagal (%s). Beralih ke fallback '%s'",
                    self.config.embedding_model, reason, self.fallback_config.embedding_model
                )
                self._using_fallback = True
                self.config = self.fallback_config
                self.client = self.fallback_client

        async def create(self, input_data: Union[str, list[str]]) -> list[float]:
            dim = self.config.embedding_dim or 1024
            if not self._using_fallback:
                try:
                    kwargs = {"input": input_data, "model": self.config.embedding_model}
                    if "gemini" in self.config.embedding_model or "text-embedding-3" in self.config.embedding_model:
                        kwargs["dimensions"] = dim
                    result = await self.client.embeddings.create(**kwargs)
                    emb = result.data[0].embedding
                    if len(emb) > dim:
                        emb = emb[:dim]
                    return emb
                except Exception as e:
                    self._activate_fallback(e)
            fb_kwargs = {"input": input_data, "model": self.fallback_config.embedding_model}
            if "text-embedding-3" in self.fallback_config.embedding_model:
                fb_kwargs["dimensions"] = dim
            result = await self.fallback_client.embeddings.create(**fb_kwargs)
            emb = result.data[0].embedding
            if len(emb) > dim:
                emb = emb[:dim]
            return emb

        async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
            if not self._using_fallback:
                try:
                    result = await self.client.embeddings.create(
                        input=input_data_list, model=self.config.embedding_model
                    )
                    return [emb.embedding[: self.config.embedding_dim] for emb in result.data]
                except Exception as e:
                    self._activate_fallback(e)
            result = await self.fallback_client.embeddings.create(
                input=input_data_list, model=self.fallback_config.embedding_model
            )
            return [emb.embedding[: self.fallback_config.embedding_dim] for emb in result.data]


class GraphitiMemoryEngine:
    """
    Engine integrasi memori temporal Graphiti & FalkorDB.
    Mendukung ingest episode secara dinamis, ekstraksi entitas temporal,
    dan query Cypher graph neuron dengan fallback aman ke database relasional (SQLite/Supabase).
    """

    FALKORDB_HOST = os.environ.get("FALKORDB_HOST", "localhost")
    FALKORDB_PORT = int(os.environ.get("FALKORDB_PORT", "6382"))
    FALKORDB_DB = os.environ.get("FALKORDB_DB", "langgraph")

    # Supabase / PostgreSQL configuration
    SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST", "127.0.0.1")
    SUPABASE_DB_PORT = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
    SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")
    SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres")
    SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "")
    SUPABASE_SCHEMA = os.environ.get("SUPABASE_SCHEMA", "langgraph")

    ROUTER_BASE_URL = resolve_router_base_url()
    ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", os.environ.get("NINE_ROUTER_API_KEY", ""))
    ROUTER_LLM_MODEL = os.environ.get("ROUTER_LLM_MODEL", "hermes")
    ROUTER_EMBED_PRIMARY = os.environ.get("ROUTER_EMBED_PRIMARY", "gemini/gemini-embedding-2-preview")
    ROUTER_EMBED_FALLBACK = os.environ.get("ROUTER_EMBED_FALLBACK", "openrouter/openai/text-embedding-3-small")
    EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

    _driver: Optional[Any] = None
    _driver_loop: Optional[asyncio.AbstractEventLoop] = None
    _graphiti: Optional[Any] = None
    _graphiti_loop: Optional[asyncio.AbstractEventLoop] = None
    _pg_pool: Optional[Any] = None
    _pg_pool_loop: Optional[asyncio.AbstractEventLoop] = None
    _falkor_available: bool = True

    @classmethod
    async def get_driver(cls) -> Optional[Any]:
        """Lazy initialization FalkorDriver singleton dengan health check singkat dan loop safety."""
        if not GRAPHITI_AVAILABLE:
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if cls._driver is not None and cls._driver_loop is current_loop:
            return cls._driver

        try:
            driver = FalkorDriver(
                host=cls.FALKORDB_HOST,
                port=cls.FALKORDB_PORT,
                database=cls.FALKORDB_DB
            )
            # Quick health check
            await driver.execute_query("RETURN 1 AS ping")
            cls._driver = driver
            cls._driver_loop = current_loop
            cls._falkor_available = True
            logger.info("FalkorDriver terhubung ke %s:%s (DB: %s)", cls.FALKORDB_HOST, cls.FALKORDB_PORT, cls.FALKORDB_DB)
            return cls._driver
        except Exception as e:
            cls._falkor_available = False
            logger.warning("FalkorDB tidak dapat dihubungi (%s). Menggunakan fallback.", e)
            return None

    @classmethod
    async def get_pg_pool(cls) -> Optional[Any]:
        """Lazy initialization asyncpg connection pool for Supabase/PostgreSQL."""
        try:
            import asyncpg
        except ImportError:
            logger.warning("asyncpg tidak terinstall; PostgreSQL pool tidak tersedia.")
            return None

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if cls._pg_pool is not None and cls._pg_pool_loop is current_loop:
            return cls._pg_pool

        try:
            pool = await asyncpg.create_pool(
                host=cls.SUPABASE_DB_HOST,
                port=cls.SUPABASE_DB_PORT,
                user=cls.SUPABASE_DB_USER,
                password=cls.SUPABASE_DB_PASSWORD,
                database=cls.SUPABASE_DB_NAME,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            # Test connection and set search_path
            async with pool.acquire() as conn:
                await conn.execute(f"SET search_path TO {cls.SUPABASE_SCHEMA}, public")
                version = await conn.fetchval("SELECT version()")
                logger.info("PostgreSQL pool terhubung ke %s:%s (schema: %s) - %s", 
                           cls.SUPABASE_DB_HOST, cls.SUPABASE_DB_PORT, cls.SUPABASE_SCHEMA, version[:80])
            cls._pg_pool = pool
            cls._pg_pool_loop = current_loop
            return cls._pg_pool
        except Exception as e:
            logger.warning("PostgreSQL pool tidak dapat dihubungi (%s). Menggunakan fallback.", e)
            return None

    @classmethod
    async def get_graphiti(cls) -> Optional[Any]:
        """Lazy initialization Graphiti instance dengan 9Router LLM dan Embedder."""
        if not GRAPHITI_AVAILABLE:
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if cls._graphiti is not None and cls._graphiti_loop is current_loop:
            return cls._graphiti

        driver = await cls.get_driver()
        if driver is None:
            return None

        try:
            llm_cfg = LLMConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                model=cls.ROUTER_LLM_MODEL,
                temperature=0.0
            )
            llm_client = OpenAIGenericClient(config=llm_cfg, structured_output_mode="json_object")

            embed_primary_cfg = OpenAIEmbedderConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                embedding_model=cls.ROUTER_EMBED_PRIMARY,
                embedding_dim=cls.EMBEDDING_DIM
            )
            embed_fallback_cfg = OpenAIEmbedderConfig(
                api_key=cls.ROUTER_API_KEY,
                base_url=cls.ROUTER_BASE_URL,
                embedding_model=cls.ROUTER_EMBED_FALLBACK,
                embedding_dim=cls.EMBEDDING_DIM
            )
            embedder = FallbackOpenAIEmbedder(embed_primary_cfg, embed_fallback_cfg)
            cross_encoder = SimpleCrossEncoder()

            # Build indices if needed
            try:
                await driver.build_indices_and_constraints()
            except Exception as idx_err:
                logger.debug("Indices/constraints info: %s", idx_err)

            # Explicit FalkorDB Vector Indices per embedding_space_id (Remediation F-004 & K-1)
            try:
                from packages.memory.embedding_fabric import ParallelEmbeddingFabric
                await ParallelEmbeddingFabric.ensure_vector_indexes(driver, dim=cls.EMBEDDING_DIM)
            except Exception as vec_err:
                logger.debug("Vector indices init notice: %s", vec_err)

            g = Graphiti(
                graph_driver=driver,
                llm_client=llm_client,
                embedder=embedder,
                cross_encoder=cross_encoder
            )
            cls._graphiti = g
            cls._graphiti_loop = current_loop
            logger.info("Graphiti Memory Engine siap dengan model LLM %s", cls.ROUTER_LLM_MODEL)
            return cls._graphiti
        except Exception as e:
            logger.error("Gagal menginisialisasi Graphiti: %s", e)
            return None

    @classmethod
    async def add_episode(
        cls,
        name: str,
        episode_body: str,
        source_description: str = "LGP API Ingestion",
        reference_time: Optional[datetime] = None,
        group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ingest episode percakapan/eksekusi ke Graphiti temporal knowledge graph."""
        ref_time = reference_time or datetime.now(timezone.utc)
        g = await cls.get_graphiti()

        if g is not None:
            try:
                res = await g.add_episode(
                    name=name,
                    episode_body=episode_body,
                    source_description=source_description,
                    reference_time=ref_time,
                    group_id=group_id
                )
                return {
                    "status": "success",
                    "engine": "graphiti_falkordb",
                    "episode_uuid": getattr(res.episode, "uuid", None),
                    "name": name,
                    "nodes_extracted": len(getattr(res, "nodes", [])),
                    "edges_extracted": len(getattr(res, "edges", [])),
                    "reference_time": ref_time.isoformat()
                }
            except Exception as e:
                logger.error("Graphiti add_episode gagal: %s. Menyimpan fallback catatan.", e)

        # Fallback recording ke database relasional agar data tidak hilang
        try:
            db = await get_db_connection()
            fact_id = f"fact-ep-{int(time.time() * 1000)}"
            now_str = datetime.now(timezone.utc).isoformat()
            async with db.execute(
                "INSERT INTO temporal_facts (fact_id, subject, predicate, object, valid_at, created_at, episode_run_id, pii_redacted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (fact_id, name, "EPISODE_RECORD", episode_body[:500], ref_time.isoformat(), now_str, group_id or "default", 0)
            ):
                await db.commit()
            await db.close()
            return {
                "status": "fallback_recorded",
                "engine": "relational_fallback",
                "fact_id": fact_id,
                "name": name,
                "nodes_extracted": 1,
                "edges_extracted": 0,
                "reference_time": ref_time.isoformat()
            }
        except Exception as db_err:
            return {
                "status": "error",
                "message": f"Episode ingestion error: {db_err}",
                "name": name
            }

    @classmethod
    async def build_neuron_graph(cls) -> Dict[str, Any]:
        """
        Membangun struktur graph neuron MiroFish.
        Mencoba query Cypher ke FalkorDB secara langsung untuk mengambil node
        dan edge bi-temporal (valid_at, invalid_at). Jika FalkorDB gagal,
        secara otomatis fallback ke query relasional (SQLite/Supabase).
        """
        driver = await cls.get_driver()
        if driver is not None:
            try:
                return await cls._build_neuron_graph_falkordb(driver)
            except Exception as e:
                logger.warning("Query Cypher FalkorDB gagal (%s). Menggunakan fallback relasional.", e)

        return await cls._build_neuron_graph_fallback()

    @classmethod
    async def _build_neuron_graph_falkordb(cls, driver: Any) -> Dict[str, Any]:
        """Ambil node & edge bi-temporal dari FalkorDB dan gabungkan dengan subagents & categories."""
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_map: set = set()

        # 1. Pasang 5 Hub Kategori Utama (Taxonomy)
        for cat in MemoryTaxonomy.CATEGORIES:
            cat_id = f"cat-{cat.lower()}"
            nodes.append({
                "id": cat_id,
                "label": cat.upper(),
                "type": "category",
                "category": cat.lower(),
                "charge": 1.0,
                "status": "active",
                "size": 24,
                "color": MemoryTaxonomy.CATEGORY_COLORS.get(cat.lower(), "#64748b"),
                "source": "taxonomy"
            })
            node_map.add(cat_id)

        # 2. Ambil 10 Subagent dari DB relasional (PostgreSQL/Supabase)
        pool = await cls.get_pg_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                subagents = await conn.fetch(
                    "SELECT id, name, role, pod, capabilities, model_policy, budget_config, trust_level FROM langgraph.subagent_registry"
                )
                for sa_row in subagents:
                    sa = dict(sa_row)
                    sa_id = f"agent-{sa['id']}"
                    nodes.append({
                        "id": sa_id,
                        "label": sa["name"],
                        "type": "subagent",
                        "category": "procedural",
                        "charge": 0.9,
                        "status": "active",
                        "size": 18,
                        "color": VisualNotation.CATEGORY_TOKENS.get("subagent", "var(--color-subagent, #0ea5e9)"),
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("subagent", "ellipse"),
                        "valid_at": datetime.now(timezone.utc).isoformat(),
                        "invalid_at": None,
                        "source": "postgresql",
                        "attributes": {
                            "role": sa["role"],
                            "pod": sa["pod"],
                            "trust_level": sa["trust_level"]
                        }
                    })
                    node_map.add(sa_id)

                    # Link subagent ke category procedural
                    edges.append({
                        "id": f"link-{sa_id}-cat-procedural",
                        "source": sa_id,
                        "target": "cat-procedural",
                        "relation": "HAS_CAPABILITY",
                        "edge_type": RDFEdgeTypes.LGP_HAS_CAPABILITY,
                        "weight": 0.8,
                        "color": VisualNotation.CATEGORY_TOKENS.get("correlation_neutral", "var(--color-corr-neutral, #64748b)"),
                        "valid_at": datetime.now(timezone.utc).isoformat(),
                        "invalid_at": None,
                        "bitemporal": True
                    })

            # 3. Ambil Inter-Neuron Correlation Edges (PostgreSQL/Supabase)
            if pool is not None:
                async with pool.acquire() as conn:
                    corr_rows = await conn.fetch(
                        "SELECT source_subagent, target_subagent, composite_weight, npmi_coactivation, polarity "
                        "FROM langgraph.correlation_edges WHERE composite_weight > 0"
                    )
                for r in corr_rows:
                    corr = dict(r)
                    src = f"agent-{corr['source_subagent']}"
                    tgt = f"agent-{corr['target_subagent']}"
                    if src in node_map and tgt in node_map:
                        edge_color = VisualNotation.CATEGORY_TOKENS.get("correlation_positive", "var(--color-corr-positive, #34d399)") if corr["polarity"] == "positive" else (
                            VisualNotation.CATEGORY_TOKENS.get("correlation_negative", "var(--color-corr-negative, #f43f5e)") if corr["polarity"] == "negative" else 
                            VisualNotation.CATEGORY_TOKENS.get("correlation_neutral", "var(--color-corr-neutral, #64748b)")
                        )
                        edges.append({
                            "id": f"corr-{corr['source_subagent']}-{corr['target_subagent']}",
                            "source": src,
                            "target": tgt,
                            "relation": f"NPMI: {corr['npmi_coactivation']:.2f}",
                            "edge_type": RDFEdgeTypes.LGP_NPMI_CORRELATION,
                            "weight": max(0.5, corr["composite_weight"] * 2),
                            "color": edge_color,
                            "animated": True,
                            "valid_at": datetime.now(timezone.utc).isoformat(),
                            "invalid_at": None,
                            "bitemporal": True
                        })

            # 4. Ambil Semua Execution Runs dari DB Relasional (Histori Episode Lengkap) - PostgreSQL
            db_runs_count = 0
            if pool is not None:
                async with pool.acquire() as conn:
                    runs_rows = await conn.fetch(
                        "SELECT run_id, thread_id, status, objective, current_subagent, created_at "
                        "FROM langgraph.runs ORDER BY created_at DESC"
                    )
                for r in runs_rows:
                    run_dict = dict(r)
                    run_id = run_dict["run_id"]
                    node_id = f"episode-{run_id}"
                    if node_id in node_map:
                        continue
                    status = run_dict.get("status") or "completed"
                    subagent = (run_dict.get("current_subagent") or "atlas").lower()
                    obj = run_dict.get("objective") or f"Run {run_id[:8]}"
                    created_at = run_dict.get("created_at")
                    created_at_str = created_at.isoformat() if created_at is not None and hasattr(created_at, "isoformat") else (str(created_at) if created_at is not None else "")
                    color = VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)") if status == "completed" else (
                        VisualNotation.CATEGORY_TOKENS.get("episode_failed", "var(--color-episode-failed, #ef4444)") if status == "failed" else
                        VisualNotation.CATEGORY_TOKENS.get("episode_running", "var(--color-episode-running, #fbbf24)")
                    )

                    nodes.append({
                        "id": node_id,
                        "label": f"Run: {obj[:22]}",
                        "type": "episode",
                        "category": "episodic",
                        "charge": 0.75,
                        "status": status,
                        "size": 13,
                        "color": color,
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("episode", "rectangle"),
                        "valid_at": created_at_str,
                        "invalid_at": None,
                        "source": "postgresql",
                        "episode_run_id": run_id,
                        "description": f"Objective: {obj} | Status: {status} | Subagent: {subagent}",
                        "attributes": {
                            "uuid": run_id,
                            "run_id": run_id,
                            "thread_id": run_dict.get("thread_id"),
                            "objective": obj,
                            "subagent": subagent,
                            "status": status,
                            "created_at": created_at_str
                        }
                    })
                    node_map.add(node_id)
                    db_runs_count += 1

                    if "cat-episodic" in node_map:
                        edges.append({
                            "id": f"link-{node_id}-cat-episodic",
                            "source": node_id,
                            "target": "cat-episodic",
                            "relation": "IS_EPISODE",
                            "edge_type": RDFEdgeTypes.LGP_IS_EPISODE,
                            "weight": 0.7,
                            "color": VisualNotation.CATEGORY_TOKENS.get("episodic", "var(--color-episodic, #3b82f6)"),
                            "valid_at": created_at_str,
                            "invalid_at": None,
                            "bitemporal": True
                        })

                    sa_node = f"agent-{subagent}"
                    if sa_node in node_map:
                        edges.append({
                            "id": f"link-{sa_node}-{node_id}",
                            "source": sa_node,
                            "target": node_id,
                            "relation": "EXECUTED",
                            "edge_type": RDFEdgeTypes.LGP_EXECUTED,
                            "weight": 1.0,
                            "color": VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)"),
                            "valid_at": created_at_str,
                            "invalid_at": None,
                            "bitemporal": True
                        })

            # 5. Ambil Semua Temporal Facts dari DB Relasional (Bi-temporal Semantic Neurons) - PostgreSQL
            db_facts_count = 0
            if pool is not None:
                async with pool.acquire() as conn:
                    facts_rows = await conn.fetch(
                        "SELECT fact_id, subject, predicate, object, valid_at, invalid_at, created_at, episode_run_id, pii_redacted "
                        "FROM langgraph.temporal_facts ORDER BY created_at DESC"
                    )
                for f_row in facts_rows:
                    fact = dict(f_row)
                    fact_id = fact["fact_id"]
                    node_id = f"entity-{fact_id}"
                    if node_id in node_map:
                        continue
                    is_invalid = fact.get("invalid_at") is not None
                    subj = str(fact.get("subject") or "Fact")
                    pred = str(fact.get("predicate") or "PROP")
                    obj = str(fact.get("object") or "")
                    valid_at = fact.get("valid_at")
                    valid_at_str = valid_at.isoformat() if valid_at is not None and hasattr(valid_at, "isoformat") else (str(valid_at) if valid_at is not None else "")
                    invalid_at = fact.get("invalid_at")
                    invalid_at_str = invalid_at.isoformat() if invalid_at is not None and hasattr(invalid_at, "isoformat") else (str(invalid_at) if invalid_at is not None else None)

                    subj_low = subj.lower()
                    cat_key = "semantic"
                    if any(k in subj_low for k in ["guard", "policy", "rule", "auth", "security", "pdp", "compliance"]):
                        cat_key = "meta"
                    elif any(k in subj_low for k in ["flow", "proc", "pipeline", "method", "action"]):
                        cat_key = "procedural"
                    elif fact.get("episode_run_id"):
                        cat_key = "episodic"

                    cat_token = VisualNotation.CATEGORY_TOKENS.get(cat_key, "var(--color-semantic, #10b981)")
                    fact_color = VisualNotation.CATEGORY_TOKENS.get("fact_invalid", "var(--color-fact-invalid, #f43f5e)") if is_invalid else cat_token
                    fact_size = 11 if is_invalid else 14
                    fact_charge = 0.5 if is_invalid else 0.85
                    fact_status = "invalid" if is_invalid else "active"

                    # Map predicate to RDF/OWL standard edge type
                    pred_lower = pred.lower()
                    edge_type = RDFEdgeTypes.LGP_HAS_FACT
                    if pred_lower in ["type", "rdf:type", "a"]:
                        edge_type = RDFEdgeTypes.RDF_TYPE
                    elif pred_lower in ["subclassof", "rdfs:subclassof"]:
                        edge_type = RDFEdgeTypes.RDFS_SUBCLASS_OF
                    elif pred_lower in ["partof", "dcterms:ispartof"]:
                        edge_type = RDFEdgeTypes.DCTERMS_IS_PART_OF
                    elif pred_lower in ["generatedby", "prov:wasgeneratedby"]:
                        edge_type = RDFEdgeTypes.PROV_WAS_GENERATED_BY
                    elif pred_lower in ["broader", "skos:broader"]:
                        edge_type = RDFEdgeTypes.SKOS_BROADER
                    elif pred_lower in ["narrower", "skos:narrower"]:
                        edge_type = RDFEdgeTypes.SKOS_NARROWER
                    elif pred_lower in ["related", "skos:related"]:
                        edge_type = RDFEdgeTypes.SKOS_RELATED
                    elif pred_lower in ["sameas", "owl:sameas"]:
                        edge_type = RDFEdgeTypes.OWL_SAME_AS

                    nodes.append({
                        "id": node_id,
                        "label": f"{subj[:18]}: {pred[:12]}",
                        "type": "fact_entity",
                        "category": cat_key,
                        "charge": fact_charge,
                        "status": fact_status,
                        "size": fact_size,
                        "color": fact_color,
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("fact_entity", "roundrectangle"),
                        "valid_at": valid_at_str,
                        "invalid_at": invalid_at_str,
                        "source": "postgresql",
                        "subject": subj,
                        "predicate": pred,
                        "object": obj,
                        "episode_run_id": fact.get("episode_run_id"),
                        "description": f"{subj} -> {pred} -> {obj[:120]}",
                        "attributes": {
                            "uuid": fact_id,
                            "subject": subj,
                            "predicate": pred,
                            "object": obj,
                            "pii_redacted": bool(fact.get("pii_redacted")),
                            "episode_run_id": fact.get("episode_run_id")
                        }
                    })
                    node_map.add(node_id)
                    db_facts_count += 1

                    cat_target = f"cat-{cat_key}"
                    if cat_target in node_map:
                        edges.append({
                            "id": f"link-{node_id}-{cat_target}",
                            "source": node_id,
                            "target": cat_target,
                            "relation": "HAS_FACT",
                            "edge_type": RDFEdgeTypes.LGP_HAS_FACT,
                            "weight": 0.6,
                            "color": VisualNotation.CATEGORY_TOKENS.get(cat_key, "var(--color-semantic, #10b981)"),
                            "valid_at": valid_at_str,
                            "invalid_at": invalid_at_str,
                            "bitemporal": True
                        })

                    ep_id = fact.get("episode_run_id")
                    if ep_id:
                        run_target = f"episode-{ep_id}"
                        if run_target in node_map:
                            edges.append({
                                "id": f"link-{run_target}-{node_id}",
                                "source": run_target,
                                "target": node_id,
                                "relation": "GENERATED_FACT",
                                "edge_type": RDFEdgeTypes.LGP_GENERATED_FACT,
                                "weight": 0.8,
                                "color": VisualNotation.CATEGORY_TOKENS.get("fact_active", "var(--color-fact-active, #10b981)"),
                                "bitemporal": True,
                                "valid_at": valid_at_str,
                                "invalid_at": invalid_at_str
                            })

                    for sa_name in ["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"]:
                        if sa_name in subj_low or sa_name in obj.lower():
                            sa_node = f"agent-{sa_name}"
                            if sa_node in node_map:
                                edges.append({
                                    "id": f"link-{sa_node}-{node_id}",
                                    "source": sa_node,
                                    "target": node_id,
                                    "relation": "RELATES_TO",
                                    "edge_type": RDFEdgeTypes.LGP_RELATES_TO,
                                    "weight": 0.7,
                                    "color": VisualNotation.CATEGORY_TOKENS.get("subagent", "var(--color-subagent, #0ea5e9)"),
                                    "valid_at": valid_at_str,
                                    "invalid_at": invalid_at_str,
                                    "bitemporal": True
                                })
        # 6. Query FalkorDB Cypher untuk Node Entitas & Episode Tambahan
        nodes_res = await driver.execute_query("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")
        falkor_nodes_raw = nodes_res[0] if nodes_res else []

        falkor_entity_count = 0
        falkor_episode_count = 0

        for row in falkor_nodes_raw:
            labels = row.get("labels", [])
            props = dict(row.get("props", {}))
            uuid = props.get("uuid")
            if not uuid:
                continue

            name = props.get("name", "Unknown")
            is_episodic = "Episodic" in labels

            if is_episodic:
                node_id = f"episode-{uuid}"
                if node_id in node_map:
                    continue
                ntype = "episode"
                ncat = "episodic"
                color = VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)")
                size = 13
                falkor_episode_count += 1
            else:
                node_id = f"entity-{uuid}"
                if node_id in node_map:
                    continue
                ntype = "fact_entity"
                ncat = "semantic"
                color = VisualNotation.CATEGORY_TOKENS.get("falkor_entity", "var(--color-falkor-entity, #a855f7)")
                size = 15
                falkor_entity_count += 1

            nodes.append({
                "id": node_id,
                "label": name,
                "type": ntype,
                "category": ncat,
                "charge": 0.85,
                "status": "active",
                "size": size,
                "color": color,
                "vowl_shape": VisualNotation.NODE_SHAPES.get(ntype, "ellipse"),
                "valid_at": props.get("valid_at") or props.get("created_at"),
                "invalid_at": props.get("invalid_at"),
                "source": "falkordb",
                "attributes": {
                    "uuid": uuid,
                    "summary": props.get("summary") or props.get("content") or "",
                    "created_at": props.get("created_at")
                }
            })
            node_map.add(node_id)

            # Link ke category hub
            cat_target = f"cat-{ncat}"
            if cat_target in node_map:
                edges.append({
                    "id": f"link-{node_id}-{cat_target}",
                    "source": node_id,
                    "target": cat_target,
                    "relation": "PART_OF",
                    "edge_type": RDFEdgeTypes.LGP_PART_OF,
                    "weight": 0.6,
                    "color": VisualNotation.CATEGORY_TOKENS.get(ncat, "var(--color-semantic, #10b981)"),
                    "valid_at": props.get("valid_at") or props.get("created_at"),
                    "invalid_at": props.get("invalid_at"),
                    "bitemporal": True
                })

            # Hubungkan ke subagent jika entitas mereferensikan nama subagent
            for sa_key in ["atlas", "clio", "vulcan", "athena", "hermes", "mnemosyne", "janus", "themis", "metron", "iris"]:
                if sa_key in name.lower():
                    sa_node = f"agent-{sa_key}"
                    if sa_node in node_map:
                        edges.append({
                            "id": f"link-{sa_node}-{node_id}",
                            "source": sa_node,
                            "target": node_id,
                            "relation": "REPRESENTATION",
                            "edge_type": RDFEdgeTypes.LGP_REPRESENTATION,
                            "weight": 1.4,
                            "color": VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)"),
                            "valid_at": props.get("valid_at") or props.get("created_at"),
                            "invalid_at": props.get("invalid_at"),
                            "bitemporal": True
                        })
                    break

        # 5. Query FalkorDB Cypher untuk Edge Bi-Temporal
        edges_res = await driver.execute_query(
            "MATCH (a)-[r]->(b) "
            "RETURN a.uuid AS src_uuid, labels(a) AS src_labels, "
            "       type(r) AS rel_type, properties(r) AS rel_props, "
            "       b.uuid AS tgt_uuid, labels(b) AS tgt_labels"
        )
        falkor_edges_raw = edges_res[0] if edges_res else []

        for row in falkor_edges_raw:
            src_uuid = row.get("src_uuid")
            tgt_uuid = row.get("tgt_uuid")
            if not src_uuid or not tgt_uuid:
                continue

            src_labels = row.get("src_labels") or []
            tgt_labels = row.get("tgt_labels") or []
            src_id = f"episode-{src_uuid}" if "Episodic" in src_labels else f"entity-{src_uuid}"
            tgt_id = f"episode-{tgt_uuid}" if "Episodic" in tgt_labels else f"entity-{tgt_uuid}"

            if src_id in node_map and tgt_id in node_map:
                rel_props = dict(row.get("rel_props") or {})
                rel_type = row.get("rel_type") or "RELATES_TO"
                relation_name = rel_props.get("name") or rel_type
                valid_at = rel_props.get("valid_at")
                invalid_at = rel_props.get("invalid_at")
                is_invalid = bool(invalid_at)

                # Map FalkorDB rel_type to RDF/OWL standard
                rel_type_lower = rel_type.lower()
                edge_type = RDFEdgeTypes.LGP_RELATES_TO
                if rel_type_lower in ["type", "rdf:type"]:
                    edge_type = RDFEdgeTypes.RDF_TYPE
                elif rel_type_lower in ["subclassof", "rdfs:subclassof"]:
                    edge_type = RDFEdgeTypes.RDFS_SUBCLASS_OF
                elif rel_type_lower in ["partof", "dcterms:ispartof", "contains"]:
                    edge_type = RDFEdgeTypes.DCTERMS_IS_PART_OF
                elif rel_type_lower in ["generatedby", "prov:wasgeneratedby"]:
                    edge_type = RDFEdgeTypes.PROV_WAS_GENERATED_BY
                elif rel_type_lower in ["mentions", "refers_to"]:
                    edge_type = RDFEdgeTypes.LGP_RELATES_TO
                elif rel_type_lower in ["represents", "representation"]:
                    edge_type = RDFEdgeTypes.LGP_REPRESENTATION
                elif rel_type_lower in ["sameas", "owl:sameas"]:
                    edge_type = RDFEdgeTypes.OWL_SAME_AS

                edge_color = VisualNotation.CATEGORY_TOKENS.get("fact_invalid", "var(--color-fact-invalid, #f43f5e)") if is_invalid else (
                    VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #60a5fa)") if rel_type == "MENTIONS" else
                    VisualNotation.CATEGORY_TOKENS.get("fact_active", "var(--color-fact-active, #10b981)")
                )

                edge_uuid = rel_props.get("uuid") or f"{src_uuid[:8]}-{tgt_uuid[:8]}_{relation_name}"
                edges.append({
                    "id": f"falkor-{edge_uuid}",
                    "source": src_id,
                    "target": tgt_id,
                    "relation": relation_name,
                    "edge_type": edge_type,
                    "detail": rel_props.get("fact") or "",
                    "valid_at": valid_at,
                    "invalid_at": invalid_at,
                    "weight": 1.2 if not is_invalid else 0.4,
                    "color": edge_color,
                    "bitemporal": True
                })

        return {
            "engine": "Graphiti v0.4 (Hybrid FalkorDB + PostgreSQL Temporal Graph)",
            "style": "MiroFish Spiking Neuron Architecture",
            "timestamp": time.time(),
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "falkordb_entities": falkor_entity_count,
                "falkordb_episodes": falkor_episode_count,
                "falkordb_edges": len(falkor_edges_raw),
                "db_runs": db_runs_count,
                "db_facts": db_facts_count,
                "subagents": 10,
                "categories": len(MemoryTaxonomy.CATEGORIES)
            }
        }

    @classmethod
    async def _build_neuron_graph_fallback(cls) -> Dict[str, Any]:
        """Fallback membangun graph neuron dari SQLite/Postgres bila FalkorDB tidak aktif."""
        db = await get_db_connection()
        try:
            nodes: List[Dict[str, Any]] = []
            edges: List[Dict[str, Any]] = []
            node_map: set = set()

            # Hub Kategori
            for cat in MemoryTaxonomy.CATEGORIES:
                cat_id = f"cat-{cat.lower()}"
                nodes.append({
                    "id": cat_id,
                    "label": cat.upper(),
                    "type": "category",
                    "category": cat.lower(),
                    "charge": 1.0,
                    "status": "active",
                    "size": 24,
                    "color": VisualNotation.CATEGORY_TOKENS.get(cat.lower(), "var(--color-meta, #64748b)"),
                    "vowl_shape": VisualNotation.NODE_SHAPES.get("category", "ellipse"),
                    "valid_at": datetime.now(timezone.utc).isoformat(),
                    "invalid_at": None
                })
                node_map.add(cat_id)

            # Subagent Registry
            async with db.execute(
                "SELECT id, name, role, pod, capabilities, model_policy, budget_config, trust_level FROM subagent_registry"
            ) as cursor:
                subagents = await cursor.fetchall()
                for sa_row in subagents:
                    sa = dict(sa_row)
                    sa_id = f"agent-{sa['id']}"
                    nodes.append({
                        "id": sa_id,
                        "label": sa["name"],
                        "type": "subagent",
                        "category": "procedural",
                        "charge": 0.9,
                        "status": "active",
                        "size": 18,
                        "color": VisualNotation.CATEGORY_TOKENS.get("subagent", "var(--color-subagent, #0ea5e9)"),
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("subagent", "ellipse"),
                        "valid_at": datetime.now(timezone.utc).isoformat(),
                        "invalid_at": None,
                        "source": "postgresql",
                        "attributes": {
                            "role": sa["role"],
                            "pod": sa["pod"],
                            "trust_level": sa["trust_level"]
                        }
                    })
                    node_map.add(sa_id)

                    edges.append({
                        "id": f"link-{sa_id}-cat-procedural",
                        "source": sa_id,
                        "target": "cat-procedural",
                        "relation": "HAS_CAPABILITY",
                        "edge_type": RDFEdgeTypes.LGP_HAS_CAPABILITY,
                        "weight": 0.8,
                        "color": VisualNotation.CATEGORY_TOKENS.get("correlation_neutral", "var(--color-corr-neutral, #64748b)"),
                        "valid_at": datetime.now(timezone.utc).isoformat(),
                        "invalid_at": None,
                        "bitemporal": True
                    })

            # Execution Runs dari DB Relasional
            async with db.execute(
                "SELECT run_id, thread_id, status, objective, current_subagent, created_at "
                "FROM runs ORDER BY created_at DESC"
            ) as cursor:
                runs_rows = await cursor.fetchall()
                for r in runs_rows:
                    run_dict = dict(r)
                    run_id = run_dict["run_id"]
                    node_id = f"episode-{run_id}"
                    if node_id in node_map:
                        continue
                    status = run_dict.get("status") or "completed"
                    subagent = (run_dict.get("current_subagent") or "atlas").lower()
                    obj = run_dict.get("objective") or f"Run {run_id[:8]}"
                    created_at = run_dict.get("created_at")
                    created_at_str = created_at.isoformat() if created_at is not None and hasattr(created_at, "isoformat") else (str(created_at) if created_at is not None else "")
                    
                    status_colors = {
                        "completed": VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)"),
                        "failed": VisualNotation.CATEGORY_TOKENS.get("episode_failed", "var(--color-episode-failed, #ef4444)"),
                        "running": VisualNotation.CATEGORY_TOKENS.get("episode_running", "var(--color-episode-running, #fbbf24)"),
                    }
                    color = status_colors.get(status, VisualNotation.CATEGORY_TOKENS.get("episode_running", "var(--color-episode-running, #fbbf24)"))

                    nodes.append({
                        "id": node_id,
                        "label": f"Run: {obj[:22]}",
                        "type": "episode",
                        "category": "episodic",
                        "charge": 0.75,
                        "status": status,
                        "size": 13,
                        "color": color,
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("episode", "rectangle"),
                        "valid_at": created_at_str,
                        "invalid_at": None,
                        "episode_run_id": run_id,
                        "description": f"Objective: {obj} | Status: {status} | Subagent: {subagent}"
                    })
                    node_map.add(node_id)

                    if "cat-episodic" in node_map:
                        edges.append({
                            "id": f"link-{node_id}-cat-episodic",
                            "source": node_id,
                            "target": "cat-episodic",
                            "relation": "IS_EPISODE",
                            "edge_type": RDFEdgeTypes.LGP_IS_EPISODE,
                            "weight": 0.7,
                            "color": VisualNotation.CATEGORY_TOKENS.get("episodic", "var(--color-episodic, #3b82f6)"),
                            "valid_at": created_at_str,
                            "invalid_at": None,
                            "bitemporal": True
                        })

                    sa_node = f"agent-{subagent}"
                    if sa_node in node_map:
                        edges.append({
                            "id": f"link-{sa_node}-{node_id}",
                            "source": sa_node,
                            "target": node_id,
                            "relation": "EXECUTED",
                            "edge_type": RDFEdgeTypes.LGP_EXECUTED,
                            "weight": 1.0,
                            "color": VisualNotation.CATEGORY_TOKENS.get("episode_completed", "var(--color-episode-completed, #38bdf8)"),
                            "valid_at": created_at_str,
                            "invalid_at": None,
                            "bitemporal": True
                        })

            # Temporal Facts dari DB
            async with db.execute("SELECT * FROM temporal_facts ORDER BY created_at DESC") as cursor:
                facts = await cursor.fetchall()
                for f_row in facts:
                    fact = dict(f_row)
                    node_id = f"entity-{fact['fact_id']}"
                    if node_id in node_map:
                        continue
                    is_invalid = fact.get("invalid_at") is not None or fact.get("status") == "invalid"
                    subj = str(fact.get("subject") or "Fact")
                    pred = str(fact.get("predicate") or "PROP")
                    obj = str(fact.get("object") or "")
                    valid_at = fact.get("valid_at")
                    valid_at_str = valid_at.isoformat() if valid_at is not None and hasattr(valid_at, "isoformat") else (str(valid_at) if valid_at is not None else "")
                    invalid_at = fact.get("invalid_at")
                    invalid_at_str = invalid_at.isoformat() if invalid_at is not None and hasattr(invalid_at, "isoformat") else (str(invalid_at) if invalid_at is not None else None)

                    subj_low = subj.lower()
                    cat_key = "semantic"
                    if any(k in subj_low for k in ["guard", "policy", "rule", "auth", "security", "pdp", "compliance"]):
                        cat_key = "meta"
                    elif any(k in subj_low for k in ["flow", "proc", "pipeline", "method", "action"]):
                        cat_key = "procedural"
                    elif fact.get("episode_run_id"):
                        cat_key = "episodic"

                    cat_token = VisualNotation.CATEGORY_TOKENS.get(cat_key, "var(--color-semantic, #10b981)")
                    fact_color = VisualNotation.CATEGORY_TOKENS.get("fact_invalid", "var(--color-fact-invalid, #f43f5e)") if is_invalid else cat_token
                    fact_size = 11 if is_invalid else 14
                    fact_charge = 0.5 if is_invalid else 0.85
                    fact_status = "invalid" if is_invalid else "active"

                    pred_lower = pred.lower()
                    edge_type = RDFEdgeTypes.LGP_HAS_FACT
                    if pred_lower in ["type", "rdf:type", "a"]:
                        edge_type = RDFEdgeTypes.RDF_TYPE
                    elif pred_lower in ["subclassof", "rdfs:subclassof"]:
                        edge_type = RDFEdgeTypes.RDFS_SUBCLASS_OF
                    elif pred_lower in ["partof", "dcterms:ispartof"]:
                        edge_type = RDFEdgeTypes.DCTERMS_IS_PART_OF
                    elif pred_lower in ["generatedby", "prov:wasgeneratedby"]:
                        edge_type = RDFEdgeTypes.PROV_WAS_GENERATED_BY
                    elif pred_lower in ["broader", "skos:broader"]:
                        edge_type = RDFEdgeTypes.SKOS_BROADER
                    elif pred_lower in ["narrower", "skos:narrower"]:
                        edge_type = RDFEdgeTypes.SKOS_NARROWER
                    elif pred_lower in ["related", "skos:related"]:
                        edge_type = RDFEdgeTypes.SKOS_RELATED
                    elif pred_lower in ["sameas", "owl:sameas"]:
                        edge_type = RDFEdgeTypes.OWL_SAME_AS

                    nodes.append({
                        "id": node_id,
                        "label": f"{subj[:18]}: {pred[:12]}",
                        "type": "fact_entity",
                        "category": cat_key,
                        "charge": fact_charge,
                        "status": fact_status,
                        "size": fact_size,
                        "color": fact_color,
                        "vowl_shape": VisualNotation.NODE_SHAPES.get("fact_entity", "roundrectangle"),
                        "subject": subj,
                        "predicate": pred,
                        "object": obj,
                        "valid_at": valid_at_str,
                        "invalid_at": invalid_at_str,
                        "episode_run_id": fact.get("episode_run_id"),
                        "description": f"{subj} -> {pred} -> {obj[:120]}",
                        "attributes": {
                            "subject": subj,
                            "predicate": pred,
                            "object": obj,
                            "episode_run_id": fact.get("episode_run_id")
                        }
                    })
                    node_map.add(node_id)

                    cat_node_id = f"cat-{cat_key}"
                    if cat_node_id in node_map:
                        edges.append({
                            "id": f"link-{node_id}-{cat_node_id}",
                            "source": node_id,
                            "target": cat_node_id,
                            "relation": "HAS_FACT",
                            "edge_type": edge_type,
                            "weight": 0.6,
                            "color": VisualNotation.CATEGORY_TOKENS.get(cat_key, "var(--color-semantic, #10b981)"),
                            "valid_at": valid_at_str,
                            "invalid_at": invalid_at_str,
                            "bitemporal": True
                        })

                    ep_id = fact.get("episode_run_id")
                    if ep_id:
                        run_target = f"episode-{ep_id}"
                        if run_target in node_map:
                            edges.append({
                                "id": f"link-{run_target}-{node_id}",
                                "source": run_target,
                                "target": node_id,
                                "relation": "GENERATED_FACT",
                                "edge_type": RDFEdgeTypes.LGP_GENERATED_FACT,
                                "weight": 0.8,
                                "color": VisualNotation.CATEGORY_TOKENS.get("fact_active", "var(--color-fact-active, #10b981)"),
                                "bitemporal": True,
                                "valid_at": valid_at_str,
                                "invalid_at": invalid_at_str
                            })

            # Correlation Edges
            async with db.execute(
                "SELECT source_subagent, target_subagent, composite_weight, npmi_coactivation, polarity "
                "FROM correlation_edges WHERE composite_weight > 0"
            ) as cursor:
                corr_rows = await cursor.fetchall()
                for r in corr_rows:
                    corr = dict(r)
                    src = f"agent-{corr['source_subagent']}"
                    tgt = f"agent-{corr['target_subagent']}"
                    if src in node_map and tgt in node_map:
                        polarity = corr["polarity"]
                        edge_color = VisualNotation.CATEGORY_TOKENS.get(
                            "correlation_positive" if polarity == "positive" else ("correlation_negative" if polarity == "negative" else "correlation_neutral"),
                            "var(--color-corr-positive, #34d399)" if polarity == "positive" else ("var(--color-corr-negative, #f43f5e)" if polarity == "negative" else "var(--color-corr-neutral, #64748b)")
                        )
                        edges.append({
                            "id": f"corr-{corr['source_subagent']}-{corr['target_subagent']}",
                            "source": src,
                            "target": tgt,
                            "relation": f"NPMI: {corr['npmi_coactivation']:.2f}",
                            "edge_type": RDFEdgeTypes.SKOS_RELATED,
                            "weight": max(0.5, corr["composite_weight"] * 2),
                            "color": edge_color,
                            "vowl_edge_style": VisualNotation.EDGE_TYPES.get(RDFEdgeTypes.SKOS_RELATED, {}).get("style", "dashed"),
                            "animated": True,
                            "valid_at": datetime.now(timezone.utc).isoformat(),
                            "invalid_at": None,
                            "bitemporal": True
                        })

            return {
                "engine": "Graphiti (SQLite/Relational Fallback)",
                "style": "MiroFish Spiking Neuron Architecture",
                "timestamp": time.time(),
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "active_facts": len([n for n in nodes if n.get("status") == "active"]),
                    "subagents": 10,
                    "categories": len(MemoryTaxonomy.CATEGORIES)
                }
            }
        finally:
            await db.close()

    @classmethod
    async def rehydrate_falkordb_from_db(cls, driver=None) -> Dict[str, Any]:
        """Menyinkronkan seluruh runs dan temporal_facts dari PostgreSQL Supabase ke graf FalkorDB."""
        if driver is None:
            driver = await cls.get_driver()
        if not driver:
            return {"status": "skipped", "reason": "FalkorDB driver offline"}

        db = await get_db_connection()
        runs_synced = 0
        facts_synced = 0
        links_synced = 0

        try:
            # 1. Sync Runs sebagai Episodic:Episode
            async with db.execute("SELECT run_id, objective, current_subagent, status, created_at FROM runs") as cursor:
                runs = await cursor.fetchall()
            for r in runs:
                rid = r["run_id"]
                obj = (r["objective"] or f"Run {rid[:8]}").replace("'", "\\'")
                subagent = (r["current_subagent"] or "atlas").lower()
                status = r["status"] or "completed"
                created_at = str(r["created_at"]) if r["created_at"] else ""
                q = (
                    f"MERGE (ep:Episodic:Episode {{uuid: '{rid}'}}) "
                    f"SET ep.name = '{obj}', ep.subagent = '{subagent}', ep.status = '{status}', "
                    f"ep.valid_at = '{created_at}', ep.created_at = '{created_at}'"
                )
                await driver.execute_query(q)
                runs_synced += 1

            # 2. Sync Facts sebagai Entity
            async with db.execute("SELECT fact_id, subject, predicate, object, valid_at, invalid_at, created_at, episode_run_id FROM temporal_facts") as cursor:
                facts = await cursor.fetchall()
            for f in facts:
                fid = f["fact_id"]
                subj = str(f["subject"] or "Fact").replace("'", "\\'")
                pred = str(f["predicate"] or "PROP").replace("'", "\\'")
                obj = str(f["object"] or "").replace("'", "\\'")
                valid_at = str(f["valid_at"]) if f["valid_at"] else ""
                invalid_at = str(f["invalid_at"]) if f["invalid_at"] else ""
                status = "invalid" if f["invalid_at"] else "active"
                q = (
                    f"MERGE (ent:Entity {{uuid: '{fid}'}}) "
                    f"SET ent.name = '{subj}', ent.subject = '{subj}', ent.predicate = '{pred}', "
                    f"ent.object = '{obj}', ent.valid_at = '{valid_at}', ent.invalid_at = '{invalid_at}', ent.status = '{status}'"
                )
                await driver.execute_query(q)
                facts_synced += 1

                ep_id = f.get("episode_run_id")
                if ep_id:
                    link_q = (
                        f"MATCH (ep:Episode {{uuid: '{ep_id}'}}), (ent:Entity {{uuid: '{fid}'}}) "
                        f"MERGE (ep)-[r:CONTAINS]->(ent) SET r.valid_at = '{valid_at}'"
                    )
                    await driver.execute_query(link_q)
                    links_synced += 1

            return {
                "status": "success",
                "runs_synced": runs_synced,
                "facts_synced": facts_synced,
                "links_synced": links_synced
            }
        finally:
            await db.close()
