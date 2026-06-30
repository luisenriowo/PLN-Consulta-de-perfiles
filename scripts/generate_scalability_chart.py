import matplotlib.pyplot as plt
import seaborn as sns

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.5))

# Plot 1: Relation Extraction
sns.barplot(x=['Baseline', 'Compiled Matcher'], y=[11.6, 80.8], ax=ax1, palette=['#cccccc', '#2b8cbe'])
ax1.set_title('Relation Extraction Throughput')
ax1.set_ylabel('Documents per second')
for i, v in enumerate([11.6, 80.8]):
    ax1.text(i, v + 2, str(v), ha='center', fontweight='bold')

# Plot 2: Graph Insertion
sns.barplot(x=['Baseline', 'DuckDB Bulk Insert'], y=[193, 1586], ax=ax2, palette=['#cccccc', '#e34a33'])
ax2.set_title('Graph Insertion Rate')
ax2.set_ylabel('Edges per second')
for i, v in enumerate([193, 1586]):
    ax2.text(i, v + 40, str(v), ha='center', fontweight='bold')

plt.suptitle('Performance Optimization at Archive Scale', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('scalability_chart.png', dpi=300, bbox_inches='tight')
print("Scalability chart generated as scalability_chart.png")
