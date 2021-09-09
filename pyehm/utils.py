# -*- coding: utf-8 -*-
from typing import Union, List, Sequence

import matplotlib.pyplot
import networkx
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
from networkx.drawing.nx_pydot import graphviz_layout
from networkx.algorithms.components.connected import connected_components


class EHMNetNode:
    """A node in the :class:`~.EHMNet` constructed by :class:`~.EHM`.

    Parameters
    ----------
    layer: :class:`int`
        Index of the network layer in which the node is placed. Since a different layer in the network is built for
        each track, this also represented the index of the track this node relates to.
    identity: :class:`set` of :class:`int`
        The identity of the node. As per Section 3.1 of [EHM1]_, "the identity for each node is an indication of how
        measurement assignments made for tracks already considered affect assignments for tracks remaining to be
        considered".
    """
    def __init__(self, layer, identity=None):
        # Index of the layer (track) in the network
        self.layer = layer
        # Identity of the node
        self.identity = identity if identity else set()
        # Index of the node when added to the network. This is set by the network and
        # should not be edited.
        self.ind = None

    def __repr__(self):
        return 'EHMNetNode(ind={}, layer={}, identity={})'.format(self.ind, self.layer, self.identity)


class EHM2NetNode(EHMNetNode):
    """A node in the :class:`~.EHMNet` constructed by :class:`~.EHM2`.

    Parameters
    ----------
    layer: :class:`int`
        Index of the network layer in which the node is placed.
    track: :class:`int`
        Index of track this node relates to.
    subnet: :class:`int`
        Index of subnet to which the node belongs.
    identity: :class:`set` of :class:`int`
        The identity of the node. As per Section 3.1 of [EHM1]_, "the identity for each node is an indication of how
        measurement assignments made for tracks already considered affect assignments for tracks remaining to be
        considered".
    """
    def __init__(self, layer, track=None, subnet=0, identity=None):
        super().__init__(layer, identity)
        # Index of track this node relates to
        self.track = track
        # Index of subnet the node belongs to
        self.subnet = subnet

    def __repr__(self):
        return 'EHM2NetNode(ind={}, layer={}, track={}, subnet={}, identity={})'.format(self.ind, self.layer,
                                                                                        self.track, self.subnet,
                                                                                        self.identity)


class EHMNet:
    """Represents the nets constructed by :class:`~.EHM` and :class:`~.EHM2`.

    Parameters
    ----------
    nodes: :class:`list` of :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
        The nodes comprising the net.
    validation_matrix: :class:`numpy.ndarray`
        An indicator matrix of shape (num_tracks, num_detections + 1) indicating the possible
        (aka. valid) associations between tracks and detections. The first column corresponds
        to the null hypothesis (hence contains all ones).
    edges: :class:`dict`
        A dictionary that represents the edges between nodes in the network. The dictionary keys are tuples of the form
        ```(parent, child)```, where ```parent``` and ```child``` are the source and target nodes respectively. The
        values of the dictionary are the measurement indices that describe the parent-child relationship.
    """
    def __init__(self, nodes, validation_matrix, edges=None):
        for n_i, node in enumerate(nodes):
            node.ind = n_i
        self._nodes = nodes
        self.validation_matrix = validation_matrix
        self.edges = edges if edges is not None else dict()
        self.parents_per_detection = dict()
        self.children_per_detection = dict()
        self.nodes_per_track = dict()

    @property
    def root(self) -> Union[EHMNetNode, EHM2NetNode]:
        """The root node of the net."""
        return self.nodes[0]

    @property
    def num_nodes(self) -> int:
        """Number of nodes in the net"""
        return len(self._nodes)

    @property
    def nodes(self) -> Union[List[EHMNetNode], List[EHM2NetNode]]:
        """The nodes comprising the net"""
        return self._nodes

    @property
    def nodes_forward(self) -> Union[Sequence[EHMNetNode], Sequence[EHM2NetNode]]:
        """The net nodes, ordered by increasing layer"""
        return sorted(self.nodes, key=lambda x: x.layer)

    @property
    def nx_graph(self) -> networkx.Graph:
        """Return NetworkX representation of the net. Mainly used for plotting the net."""
        g = nx.Graph()
        for child in sorted(self.nodes, key=lambda x: x.layer):
            parents = self.get_parents(child)
            if isinstance(child, EHM2NetNode):
                track = child.track
            else:
                track = child.layer if child.layer > -1 else None
            identity = child.identity
            g.add_node(child.ind, track=track, identity=identity)
            for parent in parents:
                label = str(self.edges[(parent, child)]).replace('{', '').replace('}', '')
                g.add_edge(parent.ind, child.ind, detections=label)
        return g

    def add_node(self, node: Union[EHMNetNode, EHM2NetNode], parent: Union[EHMNetNode, EHM2NetNode], detection: int):
        """Add a new node in the network.

        Parameters
        ----------
        node: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The node to be added.
        parent: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The parent of the node.
        detection: :class:`int`
            Index of measurement representing the parent child relationship.
        """
        # Set the node index
        node.ind = len(self.nodes)
        # Add node to graph
        self.nodes.append(node)
        # Create edge from parent to child
        self.edges[(parent, node)] = {detection}
        # Create parent-child-detection look-up
        self.parents_per_detection[(node, detection)] = {parent}
        if (parent, detection) in self.children_per_detection:
            self.children_per_detection[(parent, detection)].add(node)
        else:
            self.children_per_detection[(parent, detection)] = {node}

    def add_edge(self, parent: Union[EHMNetNode, EHM2NetNode], child: Union[EHMNetNode, EHM2NetNode], detection: int):
        """ Add edge between two nodes, or update an already existing edge by adding the detection to it.

        Parameters
        ----------
        parent: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The parent node, i.e. the source of the edge.
        child: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The child node, i.e. the target of the edge.
        detection: :class:`int`
            Index of measurement representing the parent child relationship.
        """
        if (parent, child) in self.edges:
            self.edges[(parent, child)].add(detection)
        else:
            self.edges[(parent, child)] = {detection}
        if (child, detection) in self.parents_per_detection:
            self.parents_per_detection[(child, detection)].add(parent)
        else:
            self.parents_per_detection[(child, detection)] = {parent}
        if (parent, detection) in self.children_per_detection:
            self.children_per_detection[(parent, detection)].add(child)
        else:
            self.children_per_detection[(parent, detection)] = {child}

    def get_parents(self, node: Union[EHMNetNode, EHM2NetNode]) -> Union[Sequence[EHMNetNode], Sequence[EHM2NetNode]]:
        """Get the parents of a node.

        Parameters
        ----------
        node: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The node whose parents should be returned

        Returns
        -------
        :class:`list` of :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            List of parent nodes
        """
        return [edge[0] for edge in self.edges if edge[1] == node]

    def get_children(self, node: Union[EHMNetNode, EHM2NetNode]) -> Union[Sequence[EHMNetNode], Sequence[EHM2NetNode]]:
        """Get the children of a node.

        Parameters
        ----------
        node: :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            The node whose children should be returned

        Returns
        -------
        :class:`list` of :class:`~.EHMNetNode` or :class:`~.EHM2NetNode`
            List of child nodes
        """
        return [edge[1] for edge in self.edges if edge[0] == node]

    def plot(self, ax: matplotlib.pyplot.Axes = None):
        """Plot the net.

        Parameters
        ----------
        ax: :class:`matplotlib.axes.Axes`
            Axis on which to plot the net
        """
        if ax is None:
            fig = plt.figure()
            ax = fig.gca()
        g = self.nx_graph
        pos = graphviz_layout(g, prog="dot")
        nx.draw(g, pos, ax=ax, node_size=0)
        labels = dict()
        for n in g.nodes:
            t = g.nodes[n]['track']
            s = str(g.nodes[n]['identity']) if len(g.nodes[n]['identity']) else 'Ø'
            if t is not None:
                labels[n] = '{{{}, {}}}'.format(t, s)
            else:
                labels[n] = 'Ø'
        pos_labels = {}
        for node, coords in pos.items():
            pos_labels[node] = (coords[0] + 10, coords[1])
        nx.draw_networkx_labels(g, pos_labels, ax=ax, labels=labels, horizontalalignment='left')
        edge_labels = nx.get_edge_attributes(g, 'detections')
        nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_labels)


class Tree:
    def __init__(self, track, children, detections, subtree):
        self.track = track
        self.children = children
        self.detections = detections
        self.subtree = subtree

    @property
    def depth(self):
        depth = 1
        c_depth = 0
        for child in self.children:
            child_depth = child.depth
            if child_depth > c_depth:
                c_depth = child_depth
        return depth + c_depth

    @property
    def nodes(self):
        nodes = [self]
        for child in self.children:
            nodes += child.nodes
        return nodes

    @property
    def nx_graph(self):
        g = nx.Graph()
        return self._traverse_tree_nx(self, g)

    @classmethod
    def _traverse_tree_nx(cls, tree, g, parent=None):
        child = g.number_of_nodes() + 1
        track = tree.track
        detections = tree.detections
        g.add_node(child, track=track, detections=detections)
        if parent:
            g.add_edge(parent, child)
        for sub_tree in tree.children:
            cls._traverse_tree_nx(sub_tree, g, child)
        return g

    def plot(self, ax=None):
        if ax is None:
            fig = plt.figure()
            ax = fig.gca()
        g = self.nx_graph
        pos = graphviz_layout(g, prog="dot")
        nx.draw(g, pos, ax=ax)
        labels = {n: g.nodes[n]['track'] for n in g.nodes}  # if g.nodes[n]['leaf']}
        pos_labels = {}
        for node, coords in pos.items():
            # if g.nodes[node]['leaf']:
            pos_labels[node] = (coords[0], coords[1])
        nx.draw_networkx_labels(g, pos_labels, ax=ax, labels=labels, font_color='white')


class Cluster:
    def __init__(self, rows=None, cols=None):
        self.rows = set(rows) if rows is not None else set()
        self.cols = set(cols) if cols is not None else set()


def calc_validation_and_likelihood_matrices(tracks, detections, hypotheses):
    """ Compute the validation and likelihood matrices

    Parameters
    ----------
    tracks: list of :class:`Track`
        Current tracked objects
    detections : list of :class:`Detection`
        Retrieved measurements
    hypotheses: dict
        Key value pairs of tracks with associated detections

    Returns
    -------
    :class:`np.array`
        An indicator matrix of shape (num_tracks, num_detections + 1) indicating the possible
        (aka. valid) associations between tracks and detections. The first column corresponds
        to the null hypothesis (hence contains all ones).
    :class:`np.array`
        A matrix of shape (num_tracks, num_detections + 1) containing the unnormalised
        likelihoods for all combinations of tracks and detections. The first column corresponds
        to the null hypothesis.
    """

    # Ensure tracks and detections are lists (not sets)
    tracks, detections = list(tracks), list(detections)

    # Construct validation and likelihood matrices
    # Both matrices have shape (num_tracks, num_detections + 1), where the first column
    # corresponds to the null hypothesis.
    num_tracks, num_detections = len(tracks), len(detections)
    likelihood_matrix = np.zeros((num_tracks, num_detections + 1))
    for i, track in enumerate(tracks):
        for hyp in hypotheses[track]:
            if not hyp:
                likelihood_matrix[i, 0] = hyp.weight
            else:
                j = next(d_i for d_i, detection in enumerate(detections)
                         if hyp.measurement == detection)
                likelihood_matrix[i, j + 1] = hyp.weight
    validation_matrix = likelihood_matrix > 0
    return validation_matrix, likelihood_matrix


def to_graph(lst):
    G = nx.Graph()
    for part in lst:
        # each sublist is a bunch of nodes
        G.add_nodes_from(part)
        # it also imlies a number of edges:
        G.add_edges_from(to_edges(part))
    return G


def to_edges(lst):
    """
        treat `l` as a Graph and return it's edges
        to_edges(['a','b','c','d']) -> [(a,b),(b,c),(c,d)]
    """
    if not len(lst):
        return
    it = iter(lst)
    last = next(it)
    for current in it:
        yield last, current
        last = current


def gen_clusters(v_matrix):
    """ Cluster tracks into groups that sharing detections

    Parameters
    ----------
    v_matrix: :class:`np.array`
        An indicator matrix of shape (num_tracks, num_detections + 1) indicating the possible
        (aka. valid) associations between tracks and detections. The first column corresponds
        to the null hypothesis (hence contains all ones).

    Returns
    -------
    list of :class:`Cluster` objects
        A list of :class:`Cluster` objects, where each cluster contains the indices of the rows
        (tracks) and columns (detections) pertaining to the cluster
    list of int
        A list of row (track) indices that have not been associated to any detections
    """

    # Validation matrix for all detections except null
    v_matrix_true = v_matrix[:, 1:]

    # Initiate parameters
    num_rows, num_cols = np.shape(v_matrix_true)  # Number of tracks

    # Form clusters of tracks sharing measurements
    unassoc_rows = set([i for i in range(num_rows)])
    clusters = list()

    # List of tracks gated for each detection
    v_lists = [np.flatnonzero(v_matrix_true[:, col_ind]) for col_ind in range(num_cols)]

    # Get clusters of tracks sharing common detections
    G = to_graph(v_lists)
    cluster_rows = [t for t in connected_components(G)]

    # Create cluster objects that contain the indices of tracks (rows) and detections (cols)
    for rows in cluster_rows:
        v_cols = set()
        for row_ind in rows:
            v_cols |= set(np.flatnonzero(v_matrix_true[row_ind, :])+1)
        clusters.append(Cluster(rows, v_cols))

    # Get tracks (rows) that are not associated to any detections
    assoc_rows = set([j for i in cluster_rows for j in i])
    unassoc_rows = unassoc_rows - assoc_rows

    return clusters, list(unassoc_rows)
