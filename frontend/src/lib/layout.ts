import type { GraphModel } from "src/api/types";

/** Left-to-right dependency layers with alternating barycenter sweeps. */
export const layoutGraph = (graph: GraphModel): GraphModel => {
  const ids = graph.nodes.map((node) => node.id);
  const members = (id: string) => ids.includes(id) ? [id] : graph.nodes.filter(
    (node) => node.group_id === id || node.group_id?.startsWith(`${id}.`),
  ).map((node) => node.id);
  const incoming = new Map(ids.map((id) => [id, new Set<string>()]));
  const outgoing = new Map(ids.map((id) => [id, new Set<string>()]));
  for (const edge of graph.edges) for (const source of members(edge.source)) {
    for (const target of members(edge.target)) {
      if (source === target) continue;
      incoming.get(target)?.add(source);
      outgoing.get(source)?.add(target);
    }
  }
  const degree = new Map(ids.map((id) => [id, incoming.get(id)!.size]));
  const rank = new Map(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => degree.get(id) === 0);
  for (let index = 0; index < queue.length; index++) {
    const id = queue[index];
    for (const target of outgoing.get(id)!) {
      rank.set(target, Math.max(rank.get(target)!, rank.get(id)! + 1));
      degree.set(target, degree.get(target)! - 1);
      if (degree.get(target) === 0) queue.push(target);
    }
  }
  // Invalid cyclic drafts remain renderable; validation reports their cycles.
  const layers: string[][] = [];
  for (const id of ids) (layers[rank.get(id)!] ??= []).push(id);
  const order = new Map<string, number>();
  const update = () => layers.forEach((layer) => layer.forEach((id, i) => order.set(id, i)));
  update();
  for (let sweep = 0; sweep < 8; sweep++) {
    const forward = sweep % 2 === 0;
    const indices = layers.map((_, i) => i);
    if (!forward) indices.reverse();
    for (const i of indices) {
      const score = (id: string) => {
        const neighbors = [...(forward ? incoming : outgoing).get(id)!];
        return neighbors.length ? neighbors.reduce((sum, n) => sum + order.get(n)!, 0) / neighbors.length : order.get(id)!;
      };
      const scores = new Map(layers[i].map((id) => [id, score(id)]));
      layers[i].sort((a, b) => scores.get(a)! - scores.get(b)!);
      update();
    }
  }
  const height = Math.max(0, ...layers.map((layer) => layer.length));
  const positions = new Map(layers.flatMap((layer, x) => layer.map((id, y) => [id, {
    x: 80 + x * 360, y: 70 + (y + (height - layer.length) / 2) * 150,
  }] as const)));
  return { ...graph, nodes: graph.nodes.map((node) => ({ ...node, position: positions.get(node.id)! })) };
};
