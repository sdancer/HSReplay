#!/usr/bin/env python
import re
import sys
from xml.etree import ElementTree
from xml.dom import minidom


POWERLOG_LINE_RE = re.compile(r"^D ([\d:.]+) ([^(]+)\(\) - (.+)$")
OUTPUTLOG_LINE_RE = re.compile(r"\[Power\] ()([^(]+)\(\) - (.+)$")

ENTITY_RE = re.compile("\[.*\s*id=(\d+)\s*.*\]")

CHOICES_CHOICE_RE = re.compile(r"id=(\d+) PlayerId=(\d+) ChoiceType=(\w+) CountMin=(\d+) CountMax=(\d+)$")
CHOICES_SOURCE_RE = re.compile(r"Source=(\[?.+\]?)$")
CHOICES_ENTITIES_RE = re.compile(r"Entities\[(\d+)\]=(\[.+\])$")

SEND_CHOICES_CHOICETYPE_RE = re.compile(r"id=(\d+) ChoiceType=(.+)$")
SEND_CHOICES_ENTITIES_RE = re.compile(r"m_chosenEntities\[(\d+)\]=(\[.+\])$")

OPTIONS_ENTITY_RE = re.compile(r"id=(\d+)$")
OPTIONS_OPTION_RE = re.compile(r"option (\d+) type=(\w+) mainEntity=(.*)$")
OPTIONS_SUBOPTION_RE = re.compile(r"(subOption|target) (\d+) entity=(.*)$")

SEND_OPTION_RE = re.compile(r"selectedOption=(\d+) selectedSubOption=(-1|\d+) selectedTarget=(\d+) selectedPosition=(\d+)")

ACTION_TAG_RE = re.compile(r"tag=(\w+) value=(\w+)")
ACTION_FULLENTITY_RE_1 = re.compile(r"FULL_ENTITY - Updating (\[.+\]) CardID=(\w+)?$")
ACTION_FULLENTITY_RE_2 = re.compile(r"FULL_ENTITY - Creating ID=(\d+) CardID=(\w+)?$")
ACTION_SHOWENTITY_RE = re.compile(r"SHOW_ENTITY - Updating Entity=(\[?.+\]?) CardID=(\w+)$")
ACTION_HIDEENTITY_RE = re.compile(r"HIDE_ENTITY - Entity=(\[.+\]) tag=(\w+) value=(\w+)")
ACTION_TAGCHANGE_RE = re.compile(r"TAG_CHANGE Entity=(\[?.+\]?) tag=(\w+) value=(\w+)")
ACTION_START_RE = re.compile(r"ACTION_START Entity=(\[?.+\]?) (?:SubType|BlockType)=(\w+) Index=(-1|\d+) Target=(\[?.+\]?)$")
ACTION_METADATA_RE = re.compile(r"META_DATA - Meta=(\w+) Data=(\[?.+\]?) Info=(\d+)")
ACTION_CREATEGAME_RE = re.compile(r"GameEntity EntityID=(\d+)")
ACTION_CREATEGAME_PLAYER_RE = re.compile(r"Player EntityID=(\d+) PlayerID=(\d+) GameAccountId=\[hi=(\d+) lo=(\d+)\]$")


def pretty_xml(xml):
	ret = ElementTree.tostring(xml)
	ret = minidom.parseString(ret).toprettyxml(indent="\t")
	return "\n".join(line for line in ret.split("\n") if line.strip())


class Node:
	attributes = ()

	def __init__(self, *args):
		self.nodes = []
		for k, arg in zip(("ts", ) + self.attributes, args):
			setattr(self, k, arg)

	def append(self, node):
		self.nodes.append(node)

	def xml(self):
		element = ElementTree.Element(self.tagname)
		for node in self.nodes:
			element.append(node.xml())
		for attr in self.attributes:
			if attr == "ts" and not self.timestamp:
				continue
			attrib = getattr(self, attr)
			if attrib:
				element.attrib[attr] = attrib
		return element

	def __repr__(self):
		return "<%s>" % (self.__class__.__name__)


class GameNode(Node):
	tagname = "Game"

	def __init__(self, ts):
		super().__init__(ts)
		self.first_player = None
		self.second_player = None

	def register_player_id(self, entity, id):
		# Power.log sucks, the entity IDs for players are not reliable.
		# We convert them to actual entity IDs...
		self.players[entity] = id
		self.playernodes[id].name = entity

	def update_current_player(self, entity, value):
		# 2nd method of figuring out the player ids: through the CURRENT_PLAYER tag
		if value == "0" and self.first_player:
			self.register_player_id(entity, self.first_player)
			self.second_player = [p for p in self.playernodes if p != self.first_player][0]
		elif value == "1" and self.second_player:
			self.register_player_id(entity, self.second_player)
			self.second_player = None


class GameEntityNode(Node):
	tagname = "GameEntity"
	attributes = ("id", )
	timestamp = False


class PlayerNode(Node):
	tagname = "Player"
	attributes = ("id", "playerID", "accountHi", "accountLo", "name")
	timestamp = False


class FullEntityNode(Node):
	tagname = "FullEntity"
	attributes = ("id", "cardID")
	timestamp = False


class ShowEntityNode(Node):
	tagname = "ShowEntity"
	attributes = ("entity", "cardID")
	timestamp = False


class ActionNode(Node):
	tagname = "Action"
	attributes = ("entity", "type", "index", "target")
	timestamp = True


class MetaDataNode(Node):
	tagname = "MetaData"
	attributes = ("meta", "data", "info")
	timestamp = False


class TagNode(Node):
	tagname = "Tag"
	attributes = ("tag", "value")
	timestamp = False


class TagChangeNode(Node):
	tagname = "TagChange"
	attributes = ("entity", "tag", "value")
	timestamp = False


class HideEntityNode(Node):
	tagname = "HideEntity"
	attributes = ("entity", "tag", "value")
	timestamp = True


##
# Choices

class ChoicesNode(Node):
	tagname = "Choices"
	attributes = ("entity", "playerID", "type", "min", "max", "source")
	timestamp = True


class ChoiceNode(Node):
	tagname = "Choice"
	attributes = ("index", "entity")
	timestamp = False


class SendChoicesNode(Node):
	tagname = "SendChoices"
	attributes = ("entity", "type")
	timestamp = True


##
# Options

class OptionsNode(Node):
	tagname = "Options"
	attributes = ("id", )
	timestamp = True


class OptionNode(Node):
	tagname = "Option"
	attributes = ("index", "type", "entity")
	timestamp = False


class SubOptionNode(Node):
	tagname = "SubOption"
	attributes = ("index", "entity")
	timestamp = False


class OptionTargetNode(Node):
	tagname = "Target"
	attributes = ("index", "entity")
	timestamp = False


class SendOptionNode(Node):
	tagname = "SendOption"
	attributes = ("option", "subOption", "target", "position")
	timestamp = False


class PlayerID:
	def __init__(self, game, data):
		self.game = game
		self.data = data

	def __contains__(self, other):
		return str(self).__contains__(other)

	def __str__(self):
		return self.game.players.get(self.data, "UNKNOWN PLAYER: %r" % (self.data))


class PowerLogParser:
	def __init__(self):
		self.ast = []

	def _parse_entity(self, data):
		if not data:
			return None
		sre = ENTITY_RE.match(data)
		if sre:
			id = sre.groups()[0]
			return id

		if data == "0":
			return None

		if data == "GameEntity":
			return self.game.id

		if data.isdigit():
			return data

		return self.game.players.get(data, PlayerID(self.game, data))

	def read(self, f):
		regex = None
		for line in f.readlines():
			if regex is None:
				sre = POWERLOG_LINE_RE.match(line)
				if sre:
					regex = POWERLOG_LINE_RE
				else:
					sre = OUTPUTLOG_LINE_RE.match(line)
					if sre:
						regex = OUTPUTLOG_LINE_RE
			else:
				sre = regex.match(line)

			if not sre:
				continue

			self.add_data(*sre.groups())

	def add_data(self, ts, method, data):
		# if method == "PowerTaskList.DebugPrintPower":
		if method == "GameState.DebugPrintPower":
			self.handle_data(ts, data)
		elif method == "GameState.SendChoices":
			self.handle_send_choices(ts, data)
		elif method == "GameState.DebugPrintChoices":
			self.handle_choices(ts, data)
		elif method == "GameState.DebugPrintOptions":
			self.handle_options(ts, data)
		elif method == "GameState.SendOption":
			self.handle_send_option(ts, data)

	def handle_send_choices(self, ts, data):
		data = data.lstrip()

		sre = SEND_CHOICES_CHOICETYPE_RE.match(data)
		if sre:
			id, type = sre.groups()
			node = SendChoicesNode(ts, id, type)
			self.current_node.append(node)
			self.current_send_choice_node = node
			return

		sre = SEND_CHOICES_ENTITIES_RE.match(data)
		if sre:
			index, entity = sre.groups()
			entity = self._parse_entity(entity)
			node = ChoiceNode(ts, index, entity)
			self.current_send_choice_node.append(node)
			return

		sys.stderr.write("Warning: Unhandled sent choices: %r\n" % (data))

	def handle_choices(self, ts, data):
		data = data.lstrip()

		sre = CHOICES_CHOICE_RE.match(data)
		if sre:
			entity, playerID, type, min, max = sre.groups()
			node = ChoicesNode(ts, entity, playerID, type, min, max, None)
			self.current_node.append(node)
			self.current_choice_node = node
			return

		sre = CHOICES_SOURCE_RE.match(data)
		if sre:
			entity, = sre.groups()
			entity = self._parse_entity(entity)
			self.current_choice_node.source = entity
			return

		sre = CHOICES_ENTITIES_RE.match(data)
		if sre:
			index, entity = sre.groups()
			entity = self._parse_entity(entity)
			node = ChoiceNode(ts, index, entity)
			self.current_choice_node.append(node)

	def handle_data(self, ts, data):
		# print(data)
		stripped_data = data.lstrip()
		indent_level = len(data) - len(stripped_data)
		data = stripped_data

		sre = ACTION_TAG_RE.match(data)
		if sre:
			tag, value = sre.groups()
			if tag == "CURRENT_PLAYER":
				assert isinstance(self.entity_def, PlayerNode)
				self.game.first_player = self.entity_def.id
			node = TagNode(ts, tag, value)
			assert self.entity_def
			self.entity_def.append(node)
			return

		sre = ACTION_TAGCHANGE_RE.match(data)
		if sre:
			self.entity_def = None
			entity, tag, value = sre.groups()
			if tag == "ENTITY_ID":
				if not entity.isdigit() and not entity.startswith("[") and entity != "GameEntity":
					self.game.register_player_id(entity, value)
			elif tag == "CURRENT_PLAYER":
				self.game.update_current_player(entity, value)
			entity = self._parse_entity(entity)
			node = TagChangeNode(ts, entity, tag, value)

			if self.current_node.indent_level > indent_level:
				# mismatched indent levels - closing the node
				# this can happen eg. during mulligans
				self.current_node = self.current_node.parent
			self.current_node.append(node)
			self.current_node.indent_level = indent_level
			return

		sre = ACTION_FULLENTITY_RE_1.match(data)
		if not sre:
			sre = ACTION_FULLENTITY_RE_2.match(data)
		if sre:
			entity, cardid = sre.groups()
			entity = self._parse_entity(entity)
			node = FullEntityNode(ts, entity, cardid)
			self.entity_def = node
			self.current_node.append(node)
			return

		sre = ACTION_SHOWENTITY_RE.match(data)
		if sre:
			entity, cardid = sre.groups()
			entity = self._parse_entity(entity)
			node = ShowEntityNode(ts, entity, cardid)
			self.entity_def = node
			self.current_node.append(node)
			return

		sre = ACTION_HIDEENTITY_RE.match(data)
		if sre:
			entity, tag, value = sre.groups()
			entity = self._parse_entity(entity)
			node = HideEntityNode(ts, entity, tag, value)
			self.current_node.append(node)
			return

		sre = ACTION_START_RE.match(data)
		if sre:
			entity, type, index, target = sre.groups()
			entity = self._parse_entity(entity)
			target = self._parse_entity(target)
			node = ActionNode(ts, entity, type, index, target)
			self.current_node.append(node)
			node.parent = self.current_node
			self.current_node = node
			self.current_node.indent_level = indent_level
			return

		sre = ACTION_METADATA_RE.match(data)
		if sre:
			meta, data, info = sre.groups()
			data = self._parse_entity(data)
			node = MetaDataNode(ts, meta, data, info)
			self.current_node.append(node)
			return

		sre = ACTION_CREATEGAME_RE.match(data)
		if sre:
			id, = sre.groups()
			assert id == "1"
			self.game.id = id
			node = GameEntityNode(ts, id)
			self.current_node.append(node)
			self.entity_def = node
			return

		sre = ACTION_CREATEGAME_PLAYER_RE.match(data)
		if sre:
			id, playerID, accountHi, accountLo = sre.groups()
			node = PlayerNode(ts, id, playerID, accountHi, accountLo, None)
			self.entity_def = node
			self.current_node.append(node)
			self.game.playernodes[id] = node
			return

		if data == "CREATE_GAME":
			self.create_game(ts)
			return

		if data == "ACTION_END":
			if not hasattr(self.current_node, "parent"):
				# Urgh, this happens all the time with mulligans :(
				# sys.stderr.write("Warning: Node %r has no parent\n" % (self.current_node))
				return
			self.current_node = self.current_node.parent
			return

		sys.stderr.write("Warning: Unhandled data: %r\n" % (data))

	def create_game(self, ts):
		self.game = GameNode(ts)
		self.game.players = {}
		self.game.playernodes = {}
		self.current_node = self.game
		self.current_node.indent_level = 0
		self.ast.append(self.game)

	def handle_options(self, ts, data):
		data = data.lstrip()

		sre = OPTIONS_ENTITY_RE.match(data)
		if sre:
			id, = sre.groups()
			node = OptionsNode(ts, id)
			self.current_options_node = node
			self.current_node.append(node)
			return

		sre = OPTIONS_OPTION_RE.match(data)
		if sre:
			index, type, entity = sre.groups()
			entity = self._parse_entity(entity)
			node = OptionNode(ts, index, type, entity)
			self.current_options_node.append(node)
			self.current_option_node = node
			# last_option_node lets us differenciate between
			# target for option and target for suboption
			self.last_option_node = node
			return

		sre = OPTIONS_SUBOPTION_RE.match(data)
		if sre:
			subop_type, index, entity = sre.groups()
			entity = self._parse_entity(entity)
			if subop_type == "subOption":
				node = SubOptionNode(ts, index, entity)
				self.current_option_node.append(node)
				self.last_option_node = node
			else:  # subop_type == "target"
				node = OptionTargetNode(ts, index, entity)
				self.last_option_node.append(node)
			return

		sys.stderr.write("Warning: Unimplemented options: %r\n" % (data))

	def handle_send_option(self, ts, data):
		data = data.lstrip()

		sre = SEND_OPTION_RE.match(data)
		if sre:
			option, suboption, target, position = sre.groups()
			node = SendOptionNode(ts, option, suboption, target, position)
			self.current_node.append(node)

	def toxml(self):
		root = ElementTree.Element("HearthstoneReplay")
		for game in self.ast:
			root.append(game.xml())
		return pretty_xml(root)


def main():
	fname = sys.argv[1]
	parser = PowerLogParser()

	with open(fname, "r") as f:
		parser.read(f)

	print(parser.toxml())


if __name__ == "__main__":
	main()
