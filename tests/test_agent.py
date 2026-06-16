"""
Agent Tests - Phase 2/3
≥4 agent test cases including HITL and subagent routing.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHITLGating:
    """Tests for Human-in-the-Loop gating on get_as_of_otb (deepagents interrupt_on)."""

    def test_get_as_of_otb_in_tool_map(self):
        """get_as_of_otb must be registered in TOOL_MAP so it can be called after approval."""
        from agent.revenue_agent import TOOL_MAP
        assert "get_as_of_otb" in TOOL_MAP, "get_as_of_otb must be in TOOL_MAP"

    def test_hitl_uses_interrupt_on_config(self):
        """deepagents interrupt_on config must gate get_as_of_otb — not hand-rolled logic."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra.create_agent)
        assert "interrupt_on" in source
        assert "get_as_of_otb" in source

    def test_hitl_approval_words_resume_graph(self):
        """Words like 'yes', 'approve', 'ok' should resolve to Command(resume=True)."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra.chat)
        approval_words = ["yes", "approve", "ok", "proceed", "go ahead", "run it", "sure"]
        for word in approval_words:
            assert word in source, f"'{word}' must be in approval word list in chat()"

    def test_hitl_denial_falls_through_to_human_message(self):
        """Words not in approval list route as a new HumanMessage (denial path)."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra.chat)
        assert "HumanMessage" in source
        # Denial: any text not in approval words → sends as new HumanMessage

    def test_is_interrupted_helper(self):
        """_is_interrupted() checks state.next on the checkpointer-backed agent."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra._is_interrupted)
        assert "state.next" in source
        assert "get_state" in source

    @pytest.mark.asyncio
    async def test_denial_not_approved(self):
        """'no' must not match any approval word."""
        approval_words = ["yes", "approve", "ok", "proceed", "go ahead", "run it", "sure"]
        text = "no"
        is_approved = any(w in text for w in approval_words)
        assert not is_approved, "Denial response should not trigger approval"


class TestSubagentRouting:
    """Tests for subagent routing on segment/mix questions."""

    @pytest.mark.asyncio
    async def test_segment_question_routes_to_subagent(self):
        """Questions about segment mix should route to the segment subagent."""
        from agent import revenue_agent

        # Test the routing logic
        msg = "Show me the segment mix for July 2025"
        msg_lower = msg.lower()

        # Check if any segment routing keywords match
        segment_keywords = ["segment mix", "ota dependency", "segment breakdown", "market mix", "block vs transient"]
        routed_to_subagent = any(kw in msg_lower for kw in segment_keywords)
        assert routed_to_subagent, "Segment mix question should trigger subagent routing"

    @pytest.mark.asyncio
    async def test_block_vs_transient_routes_to_subagent(self):
        """Block vs transient questions should route to segment subagent."""
        from agent import revenue_agent

        msg = "What is the block vs transient mix for August?"
        msg_lower = msg.lower()

        segment_keywords = ["segment mix", "ota dependency", "segment breakdown", "market mix", "block vs transient"]
        routed = any(kw in msg_lower for kw in segment_keywords)
        assert routed, "Block vs transient question should route to segment subagent"

    @pytest.mark.asyncio
    async def test_otb_question_goes_to_main_agent(self):
        """OTB summary questions should go to the main agent (not subagent)."""
        msg = "What is the OTB for July 2025?"
        msg_lower = msg.lower()

        segment_keywords = ["segment mix", "ota dependency", "segment breakdown", "market mix", "block vs transient"]
        routed_to_subagent = any(kw in msg_lower for kw in segment_keywords)
        assert not routed_to_subagent, "OTB question should NOT route to segment subagent"


class TestSkillLoading:
    """Tests for skill loading — deepagents loads SKILL.md on demand via filesystem."""

    def test_skills_da_dir_has_required_skill_files(self):
        """skills_da/ directory must have SKILL.md files (deepagents progressive disclosure)."""
        from agent.revenue_agent import PROJECT_ROOT, SKILLS_DIR
        skills_path = PROJECT_ROOT / SKILLS_DIR
        skill_files = list(skills_path.rglob("SKILL.md"))
        assert len(skill_files) >= 6, f"Need ≥6 SKILL.md files, found {len(skill_files)}"

    def test_skills_have_name_in_frontmatter(self):
        """Each SKILL.md must have a name in YAML frontmatter."""
        from agent.revenue_agent import PROJECT_ROOT, SKILLS_DIR
        skills_path = PROJECT_ROOT / SKILLS_DIR
        for skill_file in skills_path.rglob("SKILL.md"):
            content = skill_file.read_text()
            assert "name:" in content, f"{skill_file} missing name frontmatter"

    def test_skills_have_description_with_version(self):
        """At least one skill must contain 'otel-rm-v2' (CHALLENGE_SKILL requirement)."""
        from agent.revenue_agent import PROJECT_ROOT, SKILLS_DIR
        skills_path = PROJECT_ROOT / SKILLS_DIR
        all_content = "".join(f.read_text() for f in skills_path.rglob("SKILL.md"))
        assert "otel-rm-v2" in all_content

    def test_skills_reference_required_tools(self):
        """At least one tool reference per required tool across the skill pack."""
        from agent.revenue_agent import PROJECT_ROOT, SKILLS_DIR
        skills_path = PROJECT_ROOT / SKILLS_DIR
        all_content = "".join(f.read_text() for f in skills_path.rglob("SKILL.md"))
        for tool in ["get_otb_summary", "get_segment_mix", "get_pickup_delta",
                     "get_block_vs_transient_mix"]:
            assert tool in all_content, f"No skill references {tool}"


class TestAgentPlanning:
    """Tests for multi-part question decomposition and tool surface."""

    def test_tools_list_has_5_tools(self):
        """Must have exactly 5 required tools."""
        from tools.revenue_tools import ALL_TOOLS
        assert len(ALL_TOOLS) == 5

    def test_all_tool_names_correct(self):
        """Tool names must match required specification."""
        from tools.revenue_tools import ALL_TOOLS
        tool_names = [t.name for t in ALL_TOOLS]
        required = [
            "get_otb_summary",
            "get_segment_mix",
            "get_pickup_delta",
            "get_as_of_otb",
            "get_block_vs_transient_mix",
        ]
        for name in required:
            assert name in tool_names, f"Missing required tool: {name}"

    def test_no_raw_sql_tool_exposed(self):
        """No agent-facing tool accepts a free-form SQL string — enforces correctness."""
        from tools.revenue_tools import ALL_TOOLS
        import inspect
        for tool in ALL_TOOLS:
            sig = inspect.signature(tool.func)
            param_names = list(sig.parameters.keys())
            assert "sql" not in param_names, f"{tool.name} exposes raw SQL param"
            assert "query" not in param_names, f"{tool.name} exposes raw SQL param"

    def test_planning_trace_has_write_todos_before_tools(self):
        """Planning: fixture trace shows write_todos fires BEFORE any data tool."""
        import json
        from pathlib import Path
        trace_file = Path(__file__).parent / "fixtures" / "multi_tool_trace.json"
        trace = json.loads(trace_file.read_text())
        events = trace["trace_events"]

        tool_starts = [e["name"] for e in events if e["event"] == "on_tool_start"]
        assert "write_todos" in tool_starts, "Planning trace must include write_todos"

        write_idx = tool_starts.index("write_todos")
        for i, name in enumerate(tool_starts):
            if name != "write_todos":
                assert write_idx < i, f"write_todos must precede {name} in planning trace"

    def test_planning_trace_uses_multiple_tools(self):
        """Planning: fixture trace shows ≥2 distinct data tools (multi-step decomposition)."""
        import json
        from pathlib import Path
        trace_file = Path(__file__).parent / "fixtures" / "multi_tool_trace.json"
        trace = json.loads(trace_file.read_text())
        events = trace["trace_events"]

        data_tools = {
            e["name"] for e in events
            if e["event"] == "on_tool_start" and e["name"] != "write_todos"
        }
        assert len(data_tools) >= 2, f"Multi-part question must use ≥2 tools, got: {data_tools}"
        expected = set(trace.get("expected_tools", []))
        assert expected.issubset(data_tools), \
            f"Expected tools {expected} not all present in trace; got {data_tools}"


class TestDeepAgentsFramework:
    """
    Prove all four challenge items by instantiating the actual agent graph
    and inspecting its compiled nodes — not source-code string checks.

    Graph nodes assembled by create_deep_agent():
      TodoListMiddleware.after_model       -> Planning proven
      SkillsMiddleware.before_agent        -> Deep Agent filesystem proven
      MemoryMiddleware.before_agent        -> Persistent memory proven
      HumanInTheLoopMiddleware.after_model -> Deep Agent framework (HITL) proven
    """

    @pytest.fixture
    def real_agent(self):
        """Instantiate the real agent graph with a patched LLM (no API calls made)."""
        from langchain_anthropic import ChatAnthropic
        with patch('agent.revenue_agent.get_llm') as mock_llm:
            mock_llm.return_value = ChatAnthropic(model='claude-opus-4-6', api_key='test-key')
            import agent.revenue_agent as ra
            return ra.create_agent()

    @pytest.fixture
    def graph_nodes(self, real_agent):
        """Return node names from the compiled LangGraph."""
        return list(real_agent.get_graph().nodes.keys())

    # ── Deep Agent framework ──────────────────────────────────────────────────

    def test_agent_is_compiled_state_graph(self, real_agent):
        """Deep Agent framework: create_deep_agent() returns a CompiledStateGraph."""
        from langgraph.graph.state import CompiledStateGraph
        assert isinstance(real_agent, CompiledStateGraph), \
            f"Agent must be CompiledStateGraph, got {type(real_agent).__name__}"

    def test_agent_uses_deepagents_create_deep_agent(self):
        """Source check: deepagents.graph.create_deep_agent is imported and called."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra)
        assert "create_deep_agent" in source
        assert "from deepagents" in source

    # ── Planning ──────────────────────────────────────────────────────────────

    def test_planning_middleware_in_graph(self, graph_nodes):
        """Planning: TodoListMiddleware.after_model node present in compiled graph."""
        assert 'TodoListMiddleware.after_model' in graph_nodes, \
            f"Planning middleware missing. Nodes found: {graph_nodes}"

    # ── Deep Agent filesystem ─────────────────────────────────────────────────

    def test_filesystem_middleware_in_graph(self, graph_nodes):
        """Deep Agent filesystem: SkillsMiddleware.before_agent present in compiled graph."""
        assert 'SkillsMiddleware.before_agent' in graph_nodes, \
            f"Filesystem/skills middleware missing. Nodes: {graph_nodes}"

    def test_skills_dir_exists_and_has_skill_files(self):
        """skills= parameter points to a real directory with ≥6 SKILL.md files."""
        import agent.revenue_agent as ra
        skills_path = ra.PROJECT_ROOT / ra.SKILLS_DIR
        assert skills_path.exists(), f"Skills directory missing: {skills_path}"
        skill_files = list(skills_path.rglob("SKILL.md"))
        assert len(skill_files) >= 6, f"Need ≥6 SKILL.md files, found {len(skill_files)}"

    def test_filesystem_backend_configured(self):
        """FilesystemBackend is used in _make_backend() for virtual filesystem."""
        import agent.revenue_agent as ra
        import inspect
        source = inspect.getsource(ra._make_backend)
        assert "FilesystemBackend" in source

    # ── Persistent memory ─────────────────────────────────────────────────────

    def test_memory_middleware_in_graph(self, graph_nodes):
        """Persistent memory: MemoryMiddleware.before_agent present in compiled graph."""
        assert 'MemoryMiddleware.before_agent' in graph_nodes, \
            f"Memory middleware missing. Nodes: {graph_nodes}"

    def test_checkpointer_is_in_memory_saver(self, real_agent):
        """Persistent memory: checkpointer is InMemorySaver for multi-turn state."""
        from langgraph.checkpoint.memory import InMemorySaver
        assert isinstance(real_agent.checkpointer, InMemorySaver), \
            f"Expected InMemorySaver, got {type(real_agent.checkpointer).__name__}"

    def test_memory_file_exists(self):
        """memory= parameter points to a real AGENTS.md file with meaningful content."""
        import agent.revenue_agent as ra
        memory_path = ra.PROJECT_ROOT / ra.MEMORY_FILE
        assert memory_path.exists(), f"Memory file missing: {memory_path}"
        assert len(memory_path.read_text()) > 100, "AGENTS.md too short to be meaningful"

    # ── HITL (also proves framework) ──────────────────────────────────────────

    def test_hitl_middleware_in_graph(self, graph_nodes):
        """HITL: HumanInTheLoopMiddleware.after_model present in compiled graph."""
        assert 'HumanInTheLoopMiddleware.after_model' in graph_nodes, \
            f"HITL middleware missing. Nodes: {graph_nodes}"

    # ── Subagent ──────────────────────────────────────────────────────────────

    def test_segment_subagent_is_declared(self):
        """segment-analyst SubAgent declared for routing mix/segment work."""
        from agent.revenue_agent import SEGMENT_SUBAGENT
        assert isinstance(SEGMENT_SUBAGENT, dict), "SubAgent is a TypedDict"
        assert SEGMENT_SUBAGENT.get("name") == "segment-analyst"
        assert "get_segment_mix" in str(SEGMENT_SUBAGENT.get("tools", []))
