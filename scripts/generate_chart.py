import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import ast

# Load data
df = pd.read_csv('data/salidas/andina-v2/relation_type_clusters.csv')

# Exclude cluster 0 (generic actions) to focus on meaningful political interactions
top_clusters = df.iloc[1:11].copy()

# Extract the most frequent predicate to use as the label
def get_label(row):
    try:
        preds = ast.literal_eval(row)
        return preds[0][0].capitalize()
    except:
        return str(row)[:15]

top_clusters['Label'] = top_clusters['predicados_top'].apply(get_label)

plt.figure(figsize=(10, 6))
# Using a modern palette
sns.barplot(data=top_clusters, x='n', y='Label', palette='mako')
plt.title('Top 10 Semantic Clusters in Peruvian Political Interactions', fontsize=14, pad=15, weight='bold')
plt.xlabel('Number of Extracted Edges', fontsize=12)
plt.ylabel('Primary Predicate (Cluster Representative)', fontsize=12)

# Add value labels on the bars
for i, v in enumerate(top_clusters['n']):
    plt.text(v + 10, i, str(v), color='black', va='center', fontsize=10)

plt.tight_layout()
plt.savefig('distribution_chart.png', dpi=300, bbox_inches='tight')
print("Chart generated successfully as distribution_chart.png")
