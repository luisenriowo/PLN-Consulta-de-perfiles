import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

# Load the relations
df = pd.read_csv('data/salidas/andina-v2/relation_type_assignments.csv')

# Filter for Dina Boluarte
actor = "Dina Boluarte"
ego_edges = df[(df['origen'] == actor) | (df['destino'] == actor)].copy()

# Remove 'Presidenta' because it's usually a title/coreference node that creates noise
ego_edges = ego_edges[(ego_edges['origen'] != 'Presidenta') & (ego_edges['destino'] != 'Presidenta')]

# Find the most strongly connected entities to the actor
top_entities = pd.concat([
    ego_edges[ego_edges['origen'] == actor]['destino'],
    ego_edges[ego_edges['destino'] == actor]['origen']
]).value_counts().head(12).index

# Filter edges only among these top entities
filtered_edges = ego_edges[
    (ego_edges['origen'].isin(top_entities) | (ego_edges['origen'] == actor)) & 
    (ego_edges['destino'].isin(top_entities) | (ego_edges['destino'] == actor))
]

# Keep only the most common predicate for each directed pair to avoid overlapping text
filtered_edges = filtered_edges.groupby(['origen', 'destino']).first().reset_index()

# Create Graph
G = nx.DiGraph()
for _, row in filtered_edges.iterrows():
    G.add_edge(row['origen'], row['destino'], label=row['predicado'])

plt.figure(figsize=(10, 8))
# Seed for deterministic layout
pos = nx.spring_layout(G, k=0.9, seed=42)

# Draw normal nodes
other_nodes = [node for node in G.nodes() if node != actor]
nx.draw_networkx_nodes(G, pos, nodelist=other_nodes, node_size=1500, node_color='#b3cde3', edgecolors='#1f77b4', linewidths=2)

# Draw the ego node bigger and in a different color
nx.draw_networkx_nodes(G, pos, nodelist=[actor], node_size=2500, node_color='#fbb4ae', edgecolors='#e41a1c', linewidths=3)

# Draw edges
nx.draw_networkx_edges(G, pos, arrowstyle='-|>', arrowsize=15, edge_color='#666666', width=1.5, connectionstyle='arc3,rad=0.05')

# Draw node labels with text wrapping
import textwrap
wrapped_labels = {node: '\n'.join(textwrap.wrap(node, width=12)) for node in G.nodes()}
nx.draw_networkx_labels(G, pos, labels=wrapped_labels, font_size=9, font_family='sans-serif', font_weight='bold')

# Draw edge labels
edge_labels = {(row['origen'], row['destino']): row['predicado'] for _, row in filtered_edges.iterrows()}
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, font_color='#d73027', bbox=dict(facecolor='white', edgecolor='none', alpha=0.7))

plt.title(f'Political Ego-Network: {actor}', fontsize=16, fontweight='bold', pad=20)
plt.axis('off')
plt.tight_layout()
plt.savefig('ego_network_chart.png', dpi=300, bbox_inches='tight')
print("Ego-network graph generated as ego_network_chart.png")
