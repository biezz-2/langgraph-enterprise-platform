import { NeuronGraphData, NeuronNode, NeuronLink } from "@/types/neuron";


/**
 * Normalizes graph data, computes degree centrality (inDegree, outDegree, total degree)
 * and assigns dynamic sizing based on Obsidian degree scaling.
 */
export function processNeuronGraphData(raw: { nodes?: NeuronNode[]; edges?: NeuronLink[]; links?: NeuronLink[] }): NeuronGraphData {
  const nodes: NeuronNode[] = (raw.nodes || []).map((n) => ({ ...n }));
  const rawLinks = raw.links || raw.edges || [];

  const inDegreeMap: Record<string, number> = {};
  const outDegreeMap: Record<string, number> = {};

  nodes.forEach((n) => {
    inDegreeMap[n.id] = 0;
    outDegreeMap[n.id] = 0;
  });

  const links: NeuronLink[] = rawLinks.map((l, i) => {
    const srcId = typeof l.source === "object" && l.source !== null ? (l.source as NeuronNode).id : String(l.source);
    const tgtId = typeof l.target === "object" && l.target !== null ? (l.target as NeuronNode).id : String(l.target);

    if (srcId in outDegreeMap) outDegreeMap[srcId] = (outDegreeMap[srcId] || 0) + 1;
    if (tgtId in inDegreeMap) inDegreeMap[tgtId] = (inDegreeMap[tgtId] || 0) + 1;

    return {
      id: l.id || `link-${srcId}-${tgtId}-${i}`,
      source: srcId,
      target: tgtId,
      relation: l.relation || l.predicate || "CONNECTED_TO",
      weight: typeof l.weight === "number" ? l.weight : 1.0,
      color: l.color || "rgba(100, 116, 139, 0.4)",
      animated: l.animated ?? true,
      detail: l.detail,
    };
  });

  // Calculate dynamic degree-based sizing
  nodes.forEach((n) => {
    const inDeg = inDegreeMap[n.id] || 0;
    const outDeg = outDegreeMap[n.id] || 0;
    const deg = inDeg + outDeg;
    n.inDegree = inDeg;
    n.outDegree = outDeg;
    n.degree = deg;

    // Base sizing on node type and degree centrality
    if (!n.size || n.size <= 0) {
      if (n.type === "category" || n.type === "hub") {
        n.size = 24 + Math.sqrt(deg) * 3;
      } else if (n.type === "subagent") {
        n.size = 18 + Math.sqrt(deg) * 2.5;
      } else {
        n.size = 10 + Math.sqrt(deg) * 1.8;
      }
    }

    // Color group tagging
    if (n.status === "invalid" || (n.invalid_at && new Date(n.invalid_at).getTime() <= Date.now())) {
      n.color = "#f43f5e"; // Rose 500 for invalidated
    } else if (n.type === "subagent") {
      n.color = "#818cf8"; // Indigo 400
    } else if (n.type === "category" || n.type === "hub") {
      n.color = "#38bdf8"; // Sky 400
    } else if (n.type === "fact_entity" || n.type === "fact") {
      n.color = "#10b981"; // Emerald 500
    }
  });

  return {
    nodes,
    links,
    stats: {
      total_nodes: nodes.length,
      total_edges: links.length,
      active_facts: nodes.filter((n) => n.status !== "invalid" && (n.type === "fact_entity" || n.type === "fact")).length,
      categories: nodes.filter((n) => n.type === "category" || n.type === "hub").length,
    },
  };
}
