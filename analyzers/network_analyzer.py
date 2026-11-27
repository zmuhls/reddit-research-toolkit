#!/usr/bin/env python3
"""
Network Analysis Module for Reddit Data
Constructs and analyzes social networks from Reddit discussions.
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set, TYPE_CHECKING
from datetime import datetime
from collections import defaultdict, Counter
import logging

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None  # Set to None for type checking
    logging.warning("NetworkX not available. Network analysis will be disabled.")

# Only import for type checking to avoid runtime errors
if TYPE_CHECKING:
    from networkx import DiGraph, Graph

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logging.warning("Plotly not available. Network visualizations will be limited.")

try:
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

class NetworkAnalyzer:
    """
    Comprehensive network analysis for Reddit data including:
    - User interaction networks
    - Co-participation networks
    - Community detection
    - Network metrics and centrality analysis
    """

    def __init__(self, db_path: str, output_dir: str = "output/network_analysis"):
        """
        Initialize network analyzer.

        Args:
            db_path: Path to SQLite database
            output_dir: Directory for output files
        """
        if not NETWORKX_AVAILABLE:
            raise ImportError("NetworkX is required for network analysis. Install with: pip install networkx")

        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Extract subreddit name from database path
        self.subreddit = Path(db_path).stem.replace('_historical_data', '')

        # Network storage
        self.networks = {}

    def generate_comprehensive_analysis(self,
                                      network_types: List[str] = ['interaction', 'coparticipation'],
                                      start_date: Optional[str] = None,
                                      end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate comprehensive network analysis.

        Args:
            network_types: Types of networks to analyze
            start_date: Start date for analysis (YYYY-MM-DD)
            end_date: End date for analysis (YYYY-MM-DD)

        Returns:
            Dictionary containing analysis results and file paths
        """
        results = {
            'subreddit': self.subreddit,
            'analysis_timestamp': datetime.now().isoformat(),
            'network_types': network_types,
            'date_range': {'start': start_date, 'end': end_date},
            'networks': {},
            'files': {},
            'metrics': {}
        }

        for network_type in network_types:
            if network_type == 'interaction':
                network = self._build_interaction_network(start_date, end_date)
            elif network_type == 'coparticipation':
                network = self._build_coparticipation_network(start_date, end_date)
            else:
                logging.warning(f"Unknown network type: {network_type}")
                continue

            if network and len(network) > 0:
                self.networks[network_type] = network
                results['networks'][network_type] = self._analyze_network(network, network_type)
                results['files'][f'{network_type}_files'] = self._export_network(network, network_type)

        # Generate comparative analysis if multiple networks
        if len(self.networks) > 1:
            results['files']['comparison'] = self._compare_networks()

        # Create comprehensive report
        results['files']['html_report'] = self._create_network_report(results)

        return results

    def _build_interaction_network(self,
                                 start_date: Optional[str] = None,
                                 end_date: Optional[str] = None) -> 'DiGraph':
        """Build directed user interaction network from comments."""
        G = nx.DiGraph()

        with sqlite3.connect(self.db_path) as conn:
            # Get comment interactions
            query = """
            SELECT
                c.author as commenter,
                s.author as submission_author,
                c.submission_id,
                c.parent_id,
                c.created_utc,
                c.score,
                s.title
            FROM comments c
            JOIN submissions s ON c.submission_id = s.id OR c.submission_id = ('t3_' || s.id)
            WHERE c.author != '[deleted]' AND s.author != '[deleted]'
            AND c.author != s.author
            """

            if start_date:
                query += f" AND date(datetime(c.created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                query += f" AND date(datetime(c.created_utc, 'unixepoch')) <= '{end_date}'"

            query += " ORDER BY c.created_utc"

            df = pd.read_sql_query(query, conn)

            # Get comment-to-comment interactions
            comment_query = """
            SELECT
                c1.author as replier,
                c2.author as parent_author,
                c1.submission_id,
                c1.created_utc,
                c1.score
            FROM comments c1
            JOIN comments c2 ON c1.parent_id = ('t1_' || c2.id)
            WHERE c1.author != '[deleted]' AND c2.author != '[deleted]'
            AND c1.author != c2.author
            """

            if start_date:
                comment_query += f" AND date(datetime(c1.created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                comment_query += f" AND date(datetime(c1.created_utc, 'unixepoch')) <= '{end_date}'"

            comment_df = pd.read_sql_query(comment_query, conn)

        # Add submission interactions
        for _, row in df.iterrows():
            commenter = row['commenter']
            author = row['submission_author']

            if G.has_edge(commenter, author):
                G[commenter][author]['weight'] += 1
                G[commenter][author]['interactions'].append({
                    'type': 'comment_on_submission',
                    'timestamp': row['created_utc'],
                    'score': row['score']
                })
            else:
                G.add_edge(commenter, author, weight=1, interactions=[{
                    'type': 'comment_on_submission',
                    'timestamp': row['created_utc'],
                    'score': row['score']
                }])

        # Add comment-to-comment interactions
        for _, row in comment_df.iterrows():
            replier = row['replier']
            parent_author = row['parent_author']

            if G.has_edge(replier, parent_author):
                G[replier][parent_author]['weight'] += 1
                G[replier][parent_author]['interactions'].append({
                    'type': 'reply_to_comment',
                    'timestamp': row['created_utc'],
                    'score': row['score']
                })
            else:
                G.add_edge(replier, parent_author, weight=1, interactions=[{
                    'type': 'reply_to_comment',
                    'timestamp': row['created_utc'],
                    'score': row['score']
                }])

        # Add node attributes
        self._add_user_attributes(G)

        logging.info(f"Built interaction network: {len(G)} nodes, {G.number_of_edges()} edges")
        return G

    def _build_coparticipation_network(self,
                                     start_date: Optional[str] = None,
                                     end_date: Optional[str] = None) -> 'Graph':
        """Build undirected co-participation network."""
        G = nx.Graph()

        with sqlite3.connect(self.db_path) as conn:
            # Get users who participated in the same threads
            query = """
            SELECT
                submission_id,
                author,
                created_utc,
                score
            FROM (
                SELECT submission_id, author, created_utc, score, 'comment' as type
                FROM comments
                WHERE author != '[deleted]'
                UNION ALL
                SELECT id as submission_id, author, created_utc, score, 'submission' as type
                FROM submissions
                WHERE author != '[deleted]'
            ) combined
            """

            if start_date:
                query += f" WHERE date(datetime(created_utc, 'unixepoch')) >= '{start_date}'"
            if end_date:
                if start_date:
                    query += f" AND date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"
                else:
                    query += f" WHERE date(datetime(created_utc, 'unixepoch')) <= '{end_date}'"

            query += " ORDER BY submission_id, created_utc"

            df = pd.read_sql_query(query, conn)

        # Group by submission to find co-participants
        submission_groups = df.groupby('submission_id')['author'].apply(list).to_dict()

        for submission_id, authors in submission_groups.items():
            unique_authors = list(set(authors))

            # Create edges between all pairs of co-participants
            for i in range(len(unique_authors)):
                for j in range(i + 1, len(unique_authors)):
                    user1, user2 = unique_authors[i], unique_authors[j]

                    if G.has_edge(user1, user2):
                        G[user1][user2]['weight'] += 1
                        G[user1][user2]['shared_threads'].add(submission_id)
                    else:
                        G.add_edge(user1, user2, weight=1, shared_threads={submission_id})

        # Convert sets to lists for JSON serialization
        for u, v, data in G.edges(data=True):
            data['shared_threads'] = list(data['shared_threads'])
            data['num_shared_threads'] = len(data['shared_threads'])

        # Add node attributes
        self._add_user_attributes(G)

        logging.info(f"Built co-participation network: {len(G)} nodes, {G.number_of_edges()} edges")
        return G

    def _add_user_attributes(self, G: 'Graph'):
        """Add user attributes to network nodes."""
        with sqlite3.connect(self.db_path) as conn:
            # Get user statistics
            user_query = """
            SELECT
                username,
                post_count,
                comment_count,
                total_karma,
                status,
                account_created
            FROM users
            WHERE username IN ({})
            """.format(','.join([f"'{user}'" for user in G.nodes()]))

            try:
                user_df = pd.read_sql_query(user_query, conn)
                user_stats = user_df.set_index('username').to_dict('index')

                for node in G.nodes():
                    if node in user_stats:
                        G.nodes[node].update(user_stats[node])
                    else:
                        # Default attributes
                        G.nodes[node].update({
                            'post_count': 0,
                            'comment_count': 0,
                            'total_karma': 0,
                            'status': 'unknown'
                        })

            except Exception as e:
                logging.warning(f"Could not add user attributes: {e}")

    def _analyze_network(self, G: 'Graph', network_type: str) -> Dict[str, Any]:
        """Analyze network structure and compute metrics."""
        analysis = {
            'basic_metrics': self._compute_basic_metrics(G),
            'centrality_metrics': self._compute_centrality_metrics(G),
            'community_structure': self._detect_communities(G),
            'connectivity_analysis': self._analyze_connectivity(G)
        }

        if network_type == 'interaction':
            analysis['influence_metrics'] = self._compute_influence_metrics(G)

        return analysis

    def _compute_basic_metrics(self, G: 'Graph') -> Dict[str, Any]:
        """Compute basic network metrics."""
        metrics = {
            'num_nodes': len(G),
            'num_edges': G.number_of_edges(),
            'density': nx.density(G),
            'is_directed': G.is_directed()
        }

        if len(G) > 0:
            if G.is_directed():
                if nx.is_weakly_connected(G):
                    metrics['is_connected'] = True
                    metrics['avg_path_length'] = nx.average_shortest_path_length(G.to_undirected())
                else:
                    metrics['is_connected'] = False
                    # Compute for largest component
                    largest_wcc = max(nx.weakly_connected_components(G), key=len)
                    subgraph = G.subgraph(largest_wcc).to_undirected()
                    metrics['largest_component_size'] = len(largest_wcc)
                    metrics['avg_path_length_largest'] = nx.average_shortest_path_length(subgraph)
            else:
                if nx.is_connected(G):
                    metrics['is_connected'] = True
                    metrics['avg_path_length'] = nx.average_shortest_path_length(G)
                    metrics['diameter'] = nx.diameter(G)
                else:
                    metrics['is_connected'] = False
                    # Compute for largest component
                    largest_cc = max(nx.connected_components(G), key=len)
                    subgraph = G.subgraph(largest_cc)
                    metrics['largest_component_size'] = len(largest_cc)
                    metrics['avg_path_length_largest'] = nx.average_shortest_path_length(subgraph)
                    metrics['diameter_largest'] = nx.diameter(subgraph)

            # Degree statistics
            degrees = [d for n, d in G.degree()]
            metrics['avg_degree'] = sum(degrees) / len(degrees)
            metrics['max_degree'] = max(degrees)
            metrics['degree_assortativity'] = nx.degree_assortativity_coefficient(G)

        return metrics

    def _compute_centrality_metrics(self, G: 'Graph') -> Dict[str, Any]:
        """Compute centrality metrics for top nodes."""
        if len(G) == 0:
            return {}

        centrality_metrics = {}

        # Degree centrality
        degree_centrality = nx.degree_centrality(G)
        centrality_metrics['top_degree'] = sorted(
            degree_centrality.items(), key=lambda x: x[1], reverse=True
        )[:20]

        # Betweenness centrality (sample for large networks)
        if len(G) <= 1000:
            betweenness = nx.betweenness_centrality(G)
        else:
            betweenness = nx.betweenness_centrality(G, k=min(100, len(G)))

        centrality_metrics['top_betweenness'] = sorted(
            betweenness.items(), key=lambda x: x[1], reverse=True
        )[:20]

        # Eigenvector centrality (if network is connected enough)
        try:
            if not G.is_directed():
                largest_cc = max(nx.connected_components(G), key=len)
                if len(largest_cc) > 10:
                    subgraph = G.subgraph(largest_cc)
                    eigenvector = nx.eigenvector_centrality(subgraph, max_iter=1000)
                    centrality_metrics['top_eigenvector'] = sorted(
                        eigenvector.items(), key=lambda x: x[1], reverse=True
                    )[:20]
        except Exception as e:
            logging.warning(f"Could not compute eigenvector centrality: {e}")

        # PageRank (especially useful for directed graphs)
        pagerank = nx.pagerank(G)
        centrality_metrics['top_pagerank'] = sorted(
            pagerank.items(), key=lambda x: x[1], reverse=True
        )[:20]

        return centrality_metrics

    def _detect_communities(self, G: 'Graph') -> Dict[str, Any]:
        """Detect communities in the network."""
        if len(G) < 3:
            return {'communities': [], 'modularity': 0}

        try:
            # Use Louvain algorithm if available
            import community as community_louvain
            communities = community_louvain.best_partition(G.to_undirected())

            community_structure = {
                'method': 'louvain',
                'num_communities': len(set(communities.values())),
                'modularity': community_louvain.modularity(communities, G.to_undirected()),
                'communities': {}
            }

            # Group nodes by community
            for node, comm_id in communities.items():
                if comm_id not in community_structure['communities']:
                    community_structure['communities'][comm_id] = []
                community_structure['communities'][comm_id].append(node)

            # Add community sizes
            community_structure['community_sizes'] = {
                comm_id: len(nodes) for comm_id, nodes in community_structure['communities'].items()
            }

        except ImportError:
            # Fallback to greedy modularity communities
            try:
                communities = nx.algorithms.community.greedy_modularity_communities(G.to_undirected())
                community_structure = {
                    'method': 'greedy_modularity',
                    'num_communities': len(communities),
                    'communities': {i: list(comm) for i, comm in enumerate(communities)},
                    'community_sizes': {i: len(comm) for i, comm in enumerate(communities)}
                }

                # Calculate modularity
                community_dict = {}
                for i, comm in enumerate(communities):
                    for node in comm:
                        community_dict[node] = i

                community_structure['modularity'] = nx.algorithms.community.modularity(
                    G.to_undirected(), communities
                )

            except Exception as e:
                logging.warning(f"Community detection failed: {e}")
                return {'communities': [], 'modularity': 0}

        return community_structure

    def _analyze_connectivity(self, G: 'Graph') -> Dict[str, Any]:
        """Analyze network connectivity patterns."""
        connectivity = {}

        if len(G) == 0:
            return connectivity

        if G.is_directed():
            # Strongly connected components
            sccs = list(nx.strongly_connected_components(G))
            connectivity['num_strongly_connected_components'] = len(sccs)
            connectivity['largest_scc_size'] = len(max(sccs, key=len)) if sccs else 0

            # Weakly connected components
            wccs = list(nx.weakly_connected_components(G))
            connectivity['num_weakly_connected_components'] = len(wccs)
            connectivity['largest_wcc_size'] = len(max(wccs, key=len)) if wccs else 0

        else:
            # Connected components
            ccs = list(nx.connected_components(G))
            connectivity['num_connected_components'] = len(ccs)
            connectivity['largest_cc_size'] = len(max(ccs, key=len)) if ccs else 0

        # Clustering coefficient
        if not G.is_directed():
            connectivity['avg_clustering'] = nx.average_clustering(G)
            connectivity['transitivity'] = nx.transitivity(G)

        return connectivity

    def _compute_influence_metrics(self, G: 'DiGraph') -> Dict[str, Any]:
        """Compute influence metrics for directed networks."""
        influence = {}

        # In-degree and out-degree analysis
        in_degrees = dict(G.in_degree())
        out_degrees = dict(G.out_degree())

        influence['top_in_degree'] = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:20]
        influence['top_out_degree'] = sorted(out_degrees.items(), key=lambda x: x[1], reverse=True)[:20]

        # Influence ratio (in-degree / out-degree)
        influence_ratios = {}
        for node in G.nodes():
            out_deg = out_degrees.get(node, 0)
            in_deg = in_degrees.get(node, 0)
            if out_deg > 0:
                influence_ratios[node] = in_deg / out_deg
            elif in_deg > 0:
                influence_ratios[node] = float('inf')  # Only receives, never initiates
            else:
                influence_ratios[node] = 0

        # Replace inf with a large number for sorting
        for node, ratio in influence_ratios.items():
            if ratio == float('inf'):
                influence_ratios[node] = 1000

        influence['top_influence_ratio'] = sorted(
            influence_ratios.items(), key=lambda x: x[1], reverse=True
        )[:20]

        return influence

    def _export_network(self, G: 'Graph', network_type: str) -> Dict[str, str]:
        """Export network in multiple formats."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{self.subreddit}_{network_type}_{timestamp}"

        files = {}

        # GraphML and GEXF hold only text and numbers, so export a copy with
        # empty values dropped and lists or dictionaries reduced to a count.
        export_graph = self._export_safe_copy(G)

        # GraphML (preserves all attributes)
        graphml_path = self.output_dir / f"{base_filename}.graphml"
        nx.write_graphml(export_graph, str(graphml_path))
        files['graphml'] = str(graphml_path)

        # GEXF (for Gephi)
        gexf_path = self.output_dir / f"{base_filename}.gexf"
        nx.write_gexf(export_graph, str(gexf_path))
        files['gexf'] = str(gexf_path)

        # JSON (for web visualization)
        json_data = self._network_to_json(G)
        json_path = self.output_dir / f"{base_filename}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        files['json'] = str(json_path)

        # Edge list CSV
        csv_path = self.output_dir / f"{base_filename}_edges.csv"
        edge_data = []
        for u, v, data in G.edges(data=True):
            edge_info = {'source': u, 'target': v}
            edge_info.update(data)
            edge_data.append(edge_info)

        pd.DataFrame(edge_data).to_csv(csv_path, index=False)
        files['csv'] = str(csv_path)

        return files

    @staticmethod
    def _export_safe_copy(G: 'Graph') -> 'Graph':
        """Copy of G whose attributes GraphML and GEXF can store."""
        def clean(attributes: Dict[str, Any]) -> Dict[str, Any]:
            cleaned = {}
            for key, value in attributes.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple, set, dict)):
                    cleaned[f"{key}_count"] = len(value)
                elif isinstance(value, (str, bool, int, float)):
                    cleaned[key] = value
                elif hasattr(value, 'item'):  # numpy scalar
                    cleaned[key] = value.item()
                else:
                    cleaned[key] = str(value)
            return cleaned

        H = G.__class__()
        for node, attributes in G.nodes(data=True):
            H.add_node(node, **clean(attributes))
        for source, target, attributes in G.edges(data=True):
            H.add_edge(source, target, **clean(attributes))
        return H

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Make one attribute value JSON-serializable."""
        if isinstance(value, (set, frozenset)):
            return list(value)
        if isinstance(value, (list, tuple, dict, str, bool)) or value is None:
            return value
        if hasattr(value, 'item'):  # numpy scalar
            value = value.item()
        if isinstance(value, float) and value != value:  # NaN
            return None
        return value

    def _network_to_json(self, G: 'Graph') -> Dict[str, Any]:
        """Convert network to JSON format for web visualization."""
        # Nodes
        nodes = []
        for node, data in G.nodes(data=True):
            node_info = {'id': node, 'label': node}
            node_info.update(data)
            # Convert any non-serializable values
            for key, value in node_info.items():
                node_info[key] = self._json_safe(value)
            nodes.append(node_info)

        # Edges
        edges = []
        for u, v, data in G.edges(data=True):
            edge_info = {'source': u, 'target': v}
            edge_info.update(data)
            # Convert any non-serializable values
            for key, value in edge_info.items():
                edge_info[key] = self._json_safe(value)
            edges.append(edge_info)

        return {
            'nodes': nodes,
            'edges': edges,
            'directed': G.is_directed(),
            'metadata': {
                'num_nodes': len(nodes),
                'num_edges': len(edges),
                'generated_at': datetime.now().isoformat()
            }
        }

    def _compare_networks(self) -> str:
        """Compare multiple networks and generate comparison report."""
        if len(self.networks) < 2:
            return None

        comparison = {
            'networks': list(self.networks.keys()),
            'basic_comparison': {},
            'centrality_overlap': {},
            'community_comparison': {}
        }

        # Basic metrics comparison
        for net_type, network in self.networks.items():
            comparison['basic_comparison'][net_type] = self._compute_basic_metrics(network)

        # Centrality overlap analysis
        if len(self.networks) == 2:
            net_types = list(self.networks.keys())
            G1, G2 = self.networks[net_types[0]], self.networks[net_types[1]]

            # Find common nodes
            common_nodes = set(G1.nodes()) & set(G2.nodes())
            comparison['common_nodes'] = len(common_nodes)
            comparison['node_overlap_ratio'] = len(common_nodes) / len(set(G1.nodes()) | set(G2.nodes()))

            if common_nodes:
                # Compare centralities for common nodes
                deg_cent_1 = nx.degree_centrality(G1)
                deg_cent_2 = nx.degree_centrality(G2)

                common_centralities_1 = [deg_cent_1[node] for node in common_nodes if node in deg_cent_1]
                common_centralities_2 = [deg_cent_2[node] for node in common_nodes if node in deg_cent_2]

                if common_centralities_1 and common_centralities_2:
                    import numpy as np
                    correlation = np.corrcoef(common_centralities_1, common_centralities_2)[0, 1]
                    comparison['centrality_correlation'] = correlation

        output_path = self.output_dir / f"{self.subreddit}_network_comparison.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def _create_network_report(self, results: Dict[str, Any]) -> str:
        """Create comprehensive HTML report for network analysis."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Network Analysis Report - r/{self.subreddit}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .network-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .metric {{ display: inline-block; margin: 10px 15px 10px 0; }}
                .file-link {{ display: block; margin: 5px 0; padding: 10px; background-color: #007bff; color: white; text-decoration: none; border-radius: 3px; }}
                .file-link:hover {{ background-color: #0056b3; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Network Analysis Report: r/{self.subreddit}</h1>
                <p>Generated on: {results['analysis_timestamp']}</p>
                <p>Network Types: {', '.join(results['network_types'])}</p>
                {f"<p>Date Range: {results['date_range']['start']} to {results['date_range']['end']}</p>" if results['date_range']['start'] else ""}
            </div>
        """

        for network_type, network_data in results['networks'].items():
            html_content += f"""
            <div class="network-section">
                <h2>{network_type.title()} Network</h2>

                <h3>Basic Metrics</h3>
            """

            if 'basic_metrics' in network_data:
                metrics = network_data['basic_metrics']
                html_content += f"""
                <div class="metric"><strong>Nodes:</strong> {metrics.get('num_nodes', 0):,}</div>
                <div class="metric"><strong>Edges:</strong> {metrics.get('num_edges', 0):,}</div>
                <div class="metric"><strong>Density:</strong> {metrics.get('density', 0):.4f}</div>
                <div class="metric"><strong>Avg Degree:</strong> {metrics.get('avg_degree', 0):.2f}</div>
                <div class="metric"><strong>Connected:</strong> {metrics.get('is_connected', False)}</div>
                """

                if 'avg_path_length' in metrics:
                    html_content += f'<div class="metric"><strong>Avg Path Length:</strong> {metrics["avg_path_length"]:.2f}</div>'

            # Top central nodes
            if 'centrality_metrics' in network_data:
                centrality = network_data['centrality_metrics']

                if 'top_degree' in centrality:
                    html_content += """
                    <h3>Most Connected Users</h3>
                    <table>
                        <tr><th>User</th><th>Degree Centrality</th></tr>
                    """
                    for user, score in centrality['top_degree'][:10]:
                        html_content += f"<tr><td>{user}</td><td>{score:.4f}</td></tr>"
                    html_content += "</table>"

            # Community structure
            if 'community_structure' in network_data:
                comm_data = network_data['community_structure']
                html_content += f"""
                <h3>Community Structure</h3>
                <div class="metric"><strong>Communities:</strong> {comm_data.get('num_communities', 0)}</div>
                <div class="metric"><strong>Modularity:</strong> {comm_data.get('modularity', 0):.4f}</div>
                """

            # Files
            if f'{network_type}_files' in results['files']:
                html_content += "<h3>Export Files</h3>"
                for file_type, file_path in results['files'][f'{network_type}_files'].items():
                    filename = Path(file_path).name
                    html_content += f'<a href="{filename}" class="file-link">{file_type.upper()} Export</a>'

            html_content += "</div>"

        html_content += """
            </body>
        </html>
        """

        output_path = self.output_dir / f"{self.subreddit}_network_analysis_report.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return str(output_path)