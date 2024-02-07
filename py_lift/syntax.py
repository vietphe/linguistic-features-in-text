from cassis import *
from udapi.core.node import Node
import pprint as pp
from udapi.core.document import Document
import re
from utils.conllu import cas_to_str
from collections import Counter
from typing import List, Dict, Union, Generator, Tuple
from dkpro import *

UD_SYNTAX_TEST_STRING = """# sent_id = 299,300
# text = Solltest Du dann auf einmal kalte Füße bekommen, dann gnade Dir Gott.
1	Solltest	Solltest	AUX	VMFIN	Mood=Sub|Number=Sing|Person=2|Tense=Past|VerbForm=Fin	8	aux	_	Morph=2sit|NE=O|TopoField=LK
2	Du	du	PRON	PPER	Case=Nom|Number=Sing|PronType=Prs	8	nsubj	_	Morph=ns*2|NE=O|TopoField=MF
3	dann	dann	ADV	ADV	_	8	advmod	_	Morph=null|NE=O|TopoField=MF
4	auf	auf	ADP	APPR	Case=Acc	5	case	_	Morph=a|NE=O|TopoField=MF
5	einmal	einmal	ADV	ADV	_	8	obl	_	Morph=null|NE=O|TopoField=MF
6	kalte	kalt	ADJ	ADJA	Case=Acc|Gender=Masc|Number=Plur	7	amod	_	Morph=apm|NE=O|TopoField=MF
7	Füße	Fuß	NOUN	NN	Case=Acc|Gender=Masc|Number=Plur	8	obj	_	Morph=apm|NE=O|TopoField=MF
8	bekommen	bekommen	VERB	VVINF	_	11	advcl	_	Morph=null|NE=O|SpaceAfter=No|TopoField=VC
9	,	,	PUNCT	$,	_	8	punct	_	Morph=null|NE=O|TopoField=null
10	dann	dann	ADV	ADV	_	11	advmod	_	Morph=null|NE=O|TopoField=VF
11	gnade	gnaden	VERB	VVFIN	Mood=Sub|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin	0	root	_	Morph=3sks|NE=O|TopoField=LK
12	Dir	du	PRON	PPER	Case=Dat|Number=Sing|PronType=Prs	11	obj	_	Morph=ds*2|NE=O|TopoField=MF
13	Gott	Gott	PROPN	NE	Case=Nom|Gender=Masc|Number=Sing	11	nsubj	_	Morph=nsm|NE=B-OTH|SpaceAfter=No|TopoField=MF
14	.	.	PUNCT	$.	_	11	punct	_	Morph=null|NE=O|SpaceAfter=No|TopoField=null

"""


# TODO should be in resource file
FINITE_VERBS_STTS = ["VVFIN", "VMFIN", "VAFIN"]
FINITE_VERB_STTS_BROAD = ["VVFIN", "VVIMP", "VMFIN", "VAFIN", "VMIMP", "VAIMP"]
TIGER_SUBJ_LABELS = ["SB", "EP"]  # the inclusion of expletives (EP) is sorta debatable
TIGER_LEX_NOUN_POS = ["NN", "NE"]

class StuffRegistry:
	def __init__(self):
		self.dependency_length_distribution_per_rel_type = {}
		self.sent_lengths = []  # list of int
		self.tree_depths = []  # list of int
		self.finite_verb_counts = []  # list of int
		self.total_verb_counts = []  # list of int
		self.subj_before_vfin = []  # list of bool
		self.lex_np_sizes = []  # list of int

class FE_CasToTree:
	def __init__(self, layer, ts):
		self.ts = ts
		self.layer = layer

	def extract(self, cas):
		
		# TODO why "vu"?
		vu = cas.get_view(self.layer)

		registry = StuffRegistry()

		# TODO: get rid of the magic number below; only used for debugging
		MAXSENT = 2000
		sct = 0
		for sent in vu.select(T_SENT):
			
			self._register_stuff(vu, registry, sent)

			sct += 1
			if sct > MAXSENT:
				break

		NUM_FEATURE = "org.lift.type.FeatureAnnotationNumeric"
		print(
			"Dependency length distribution per relation type\n"
			+ pp.pformat(registry.dependency_length_distribution_per_rel_type)
		)
		(
			avg_left_dep_len,
			avg_right_dep_len,
			avg_all_dep_len,
		) = self._get_dependency_lengths_across_all_rels_in_doc(
			registry.dependency_length_distribution_per_rel_type
		)

		print("average dependency length leftward %s" % avg_left_dep_len)
		self._add_feat_to_cas(
			cas, 
			"Average_Dependeny_Length_Left", 
			NUM_FEATURE, 
			avg_left_dep_len
		)

		print("average dependency length rightward %s" % avg_right_dep_len)
		self._add_feat_to_cas(
			cas, 
			"Average_Dependeny_Length_Right", 
			NUM_FEATURE, 
			avg_right_dep_len
		)

		print("average dependency length all %s" % avg_all_dep_len)
		self._add_feat_to_cas(
			cas, 
			"Average_Dependeny_Length_All", 
			NUM_FEATURE, 
			avg_all_dep_len
		)

		print("sent lengths %s" % registry.sent_lengths)
		avg_sent_len = round(float(sum(registry.sent_lengths)) / len(registry.sent_lengths), 2)
		self._add_feat_to_cas(
			cas,
			"Average_Sentence_Length", 
			NUM_FEATURE, 
			avg_sent_len
		)

		print("tree_depths %s" % registry.tree_depths)
		avg_tree_depth = round(float(sum(registry.tree_depths)) / len(registry.tree_depths), 2)
		self._add_feat_to_cas(
			cas, 
			"Average_Tree_Depth",
			NUM_FEATURE, 
			avg_tree_depth
		)

		print("finite_verb_counts %s" % registry.finite_verb_counts)
		try:
			avg_finite_verbs = round(
				float(sum(registry.finite_verb_counts)) / len(registry.finite_verb_counts), 2
			)
		except:
			avg_finite_verbs = 0
		self._add_feat_to_cas(
			cas, 
			"Average_Number_Of_Finite_Verbs", 
			NUM_FEATURE, 
			avg_finite_verbs
		)

		print("total_verb_counts %s" % registry.total_verb_counts)
		try:
			avg_verb_count = round(
				float(sum(registry.total_verb_counts)) / len(registry.total_verb_counts), 2
			)
		except:
			avg_verb_count = 0
		self._add_feat_to_cas(
			cas, 
			"Average_Number_Of_Verbs", 
			NUM_FEATURE, 
			avg_verb_count
		)

		print("subj_before_vfin %s" % registry.subj_before_vfin)
		invc = Counter(registry.subj_before_vfin)
		try:
			share_of_s_vfin_inversions = invc[True] / invc[False]
		except:
			share_of_s_vfin_inversions = 0

		self._add_feat_to_cas(
			cas, "Proportion_of_Subj_Vfin_Inversions",
			NUM_FEATURE,
			share_of_s_vfin_inversions,
		)

		print("lex_np_sizes %s" % registry.lex_np_sizes)
		try:
			avg_lex_np_size = round(float(sum(registry.lex_np_sizes)) / len(registry.lex_np_sizes), 2)
		except:
			avg_lex_np_size = 0
		self._add_feat_to_cas(
			cas, 
			"Average_Size_Of_Lexical_NP", 
			NUM_FEATURE, 
			avg_lex_np_size
		)
		return True

	def _add_feat_to_cas(self, cas, name, featpath, value):
		F = self.ts.get_type(featpath)
		feature = F(name=name, value=value)
		cas.add(feature)

	def _register_stuff(self, cas, registry: StuffRegistry, sent):

		udapi_doc = Document()
		udapi_doc.from_conllu_string(cas_to_str(cas, sent))

		# udapi_doc.from_conllu_string(TEST_STRING)
		for bundle in udapi_doc.bundles:
			tree = bundle.get_tree()
			print(tree.compute_text())
			# finite verbs are identifed by their xpos-tag; we're not looking at any info in the morphological feats
			registry.finite_verb_counts.append(
				self._count_nodes_with_specified_values_for_feat(
					tree, "xpos", [".*FIN"]
				)
			)
			# all verbal forms have a pos-Tag beginning with "V"
			registry.total_verb_counts.append(
				self._count_nodes_with_specified_values_for_feat(
					tree, "xpos", ["V.*"]
				)
			)
			registry.subj_before_vfin.extend(self._check_s_before_vfin(tree))

			registry.tree_depths.append(self._get_max_subtree_depth(tree))
			registry.sent_lengths.append(len(tree.descendants))
			registry.lex_np_sizes.extend(self._get_lex_np_sizes(tree))

			# Not used for now
			# print(list(self.get_triples(tree, feats=["xpos","deprel"])))

			registry.dependency_length_distribution_per_rel_type = self._update_dep_dist(
				tree, registry.dependency_length_distribution_per_rel_type
			)

	def _get_average_from_counter(self, mycounter):
		""" get average value from counter """
		insts = 0
		totlen = 0
		for lng in mycounter:
			totlen += mycounter[lng] * lng
			insts += mycounter[lng]
		try:
			avg_dep_len = round(float(totlen / insts), 2)
		except:
			avg_dep_len = 0

		return avg_dep_len

	# def get_dependency_lengths_across_all_rels_in_doc(counts_per_rel):
	def _get_dependency_lengths_across_all_rels_in_doc(
		self, counts_per_rel: Dict
	) -> Tuple:
		"""
		Merge the information from individual counters per relation type.
		Do this once for each dependency direction and then do this for absolute values.
		Returns three average dependency length values.
		"""
		leftward = Counter()
		rightward = Counter()
		for rel in counts_per_rel.keys():
			ctr = counts_per_rel[rel]
			for kee in ctr.keys():
				if kee < 0:
					leftward.update({abs(kee): ctr[kee]})
				else:
					rightward.update({kee: ctr[kee]})
		anydir = Counter()
		anydir.update(leftward)
		anydir.update(rightward)
		avg_all = self._get_average_from_counter(anydir)
		avg_left = self._get_average_from_counter(leftward)
		avg_right = self._get_average_from_counter(rightward)

		return (avg_left, avg_right, avg_all)


	def _get_max_subtree_depth(self, node: Node) -> int:
		""" determine depth of the subtree rooted at the given node """
		return max([child._get_attr("depth") for child in node.descendants])

	def _count_nodes_with_specified_values_for_feat(
		self, node, featname, wanted_values
	) -> int:
		"""count nodes with specified values for a given feature; values are regex"""
		return len(
			set(
				[
					child
					for child in node.descendants
					for wv in wanted_values
					if re.match(wv, child._get_attr(featname))
				]
			)
		)

	def _update_dep_dist(self, node, dep_dist) -> Dict:
		"""Update the document-level distribution of dependency lenghts per dependency type by processing the nodes in the tree.
		Dep length is the difference between the indices of the head and the dependent. Deps adjacent to their heads have a dep length of |1| , etc.
		The values can be pos and neg: they're positive if the dependent is to the right of the head, and negative if it's the other way around.
		We're not merging the two cases by using absolute values!
		"""
		for d in node.descendants:
			rel = d.deprel
			cix = d.ord
			pix = d.parent.ord
			diff = cix - pix
			if not rel in dep_dist:
				dep_dist[rel] = Counter()
			dep_dist[rel][diff] += 1
		return dep_dist

	def _get_triples(self, node: Node, feats=["form", "upos"]) -> Generator:
		"""Yields triples of the form: (head, dependency_rel, dep) where head and dep are tuples
		containing the attributes specified in the feats parameter.
		Default feats are "form" and "upos".
		"""
		head = tuple(node.get_attrs(feats, stringify=False))
		for i in node.children:
			dep = tuple(i.get_attrs(feats, stringify=False))
			yield (head, i.deprel, dep)
			yield from self._get_triples(i, feats=feats)

	def _get_lex_np_sizes(
		self, tree: Node, lex_noun_pos_tags=TIGER_LEX_NOUN_POS
	) -> List[int]:
		"""get the number of tokens that make up the lexical noun phrases in the sentence/tree"""
		size_list = []
		for d in tree.descendants:
			if d.xpos in lex_noun_pos_tags:
				n_size = 1 + len(d.descendants)
				size_list.append(n_size)
		return size_list

	def _check_s_before_vfin(
		self, node: Node, finiteverbtags=FINITE_VERBS_STTS, subjlabels=TIGER_SUBJ_LABELS
	) -> List[bool]:
		"""
		True or false depending on whether a subject precedes its finite verb .
		If a verb lacks a subject, it's disregarded.
		The lists of pos tags for finite verbs and of subj relation labels may need to be adjusted per tagger/parser used!
		"""
		s_inv_list = []
		for d in node.descendants:
			if d.xpos in finiteverbtags:
				print(d.form, d.upos, d.xpos)
				for kid in d.children:
					if kid.deprel in subjlabels:
						if kid.ord > d.ord:
							s_inv_list.append(True)
						else:
							s_inv_list.append(False)
		return s_inv_list