import copy
from types import SimpleNamespace

import discord
import pytest
from discord import ui


@pytest.mark.asyncio
@pytest.mark.parametrize('in_container', [False, True])
@pytest.mark.parametrize('allowed', [False, True])
async def test_row_decorators_run_parent_checks(in_container, allowed):
    calls = []

    class Row(ui.ActionRow):
        async def interaction_check(self, interaction):
            calls.append('row')
            return allowed

    base = ui.Container if in_container else ui.LayoutView

    class Owner(base):
        row = Row()

        @row.button(label='Action', custom_id='action')
        async def action(self, interaction, button):
            calls.append(('callback', self, button))

        async def interaction_check(self, interaction):
            calls.append('owner')
            return True

    owner = Owner()
    view = ui.LayoutView(timeout=None) if in_container else owner
    if in_container:
        view.add_item(owner)
    child = owner.row.children[0]
    assert child.parent is owner.row
    await view._scheduled_task(child, SimpleNamespace(data={}))
    assert calls == (['row', 'owner', ('callback', owner, child)] if allowed else ['row'])


@pytest.mark.asyncio
@pytest.mark.parametrize('select', [False, True])
@pytest.mark.parametrize('in_container', [False, True])
async def test_copied_rows_dispatch_to_the_checked_instance(select, in_container):
    calls = []
    decorator = (
        ui.select(custom_id='action', options=[discord.SelectOption(label='A', value='a')])
        if select else ui.button(label='Action', custom_id='action')
    )

    class Row(ui.ActionRow):
        owner = 0

        async def interaction_check(self, interaction):
            calls.append(('check', self.owner))
            return interaction.user.id == self.owner

        @decorator
        async def action(self, interaction, item):
            calls.append(('callback', self.owner, item))

    class Container(ui.Container):
        row = Row()

    class View(ui.LayoutView):
        component = Container() if in_container else Row()

    first, second = View(timeout=None), View(timeout=None)
    first_row = first.component.row if in_container else first.component
    second_row = second.component.row if in_container else second.component
    first_row.owner, second_row.owner = 111, 222
    first_item, second_item = first_row.children[0], second_row.children[0]
    assert first_item.callback is not second_item.callback
    assert first_row.action is first_item
    assert second_row.action is second_item

    interaction = SimpleNamespace(data={'values': ['a']}, user=SimpleNamespace(id=111))
    await first._scheduled_task(first_item, interaction)
    assert calls == [('check', 111), ('callback', 111, first_item)]
    calls.clear()
    await second._scheduled_task(second_item, interaction)
    assert calls == [('check', 222)]


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['container', 'section'])
@pytest.mark.parametrize('attached', [False, True])
async def test_copy_uses_the_copied_parent_policy(kind, attached):
    calls = []

    class Policy:
        allowed = True

        async def interaction_check(self, interaction):
            calls.append(self.allowed)
            return self.allowed

    class Container(Policy, ui.Container):
        pass

    class Section(Policy, ui.Section):
        pass

    button = ui.Button(label='Action', custom_id='action')
    original = Container(ui.ActionRow(button)) if kind == 'container' else Section('Text', accessory=button)
    original_view = ui.LayoutView(timeout=None)
    if attached:
        original_view.add_item(original)
    copied = original.copy()
    copied.allowed = False
    view = ui.LayoutView(timeout=None)
    view.add_item(copied)
    child = copied.children[0].children[0] if kind == 'container' else copied.accessory

    async def callback(interaction):
        calls.append('callback')

    child.callback = callback
    await view._scheduled_task(child, SimpleNamespace(data={}))
    assert calls == [False]
    assert (copied.children[0].parent if kind == 'container' else child.parent) is copied
    assert child.view is view
    assert button.parent is (original.children[0] if kind == 'container' else original)
    assert button.view is (original_view if attached else None)


@pytest.mark.asyncio
async def test_copied_container_decorator_retains_container_callback_owner():
    calls = []

    class Container(ui.Container):
        row = ui.ActionRow()

        @row.button(label='Action', custom_id='action')
        async def action(self, interaction, button):
            calls.append((self, button, self.action))

    class View(ui.LayoutView):
        container = Container()

    view = View(timeout=None)
    child = view.container.row.children[0]
    await view._scheduled_task(child, SimpleNamespace(data={}))
    assert calls == [(view.container, child, child)]


def test_button_copy_leaves_original_callback_binding_intact():
    class Row(ui.ActionRow):
        @ui.button(label='Action', custom_id='action')
        async def action(self, interaction, button):
            pass

    row = Row()
    original = row.action
    copied = original.copy()
    assert original.callback.item is original
    assert copied.callback.item is copied
    assert original.callback.parent is copied.callback.parent is row
    assert original.custom_id == copied.custom_id
    assert ui.Button().copy().custom_id is not None


def test_select_copy_does_not_share_options_or_state():
    original = ui.Select(options=[discord.SelectOption(label='A')], custom_id='select')
    original._values = ['A']
    copied = original.copy()
    copied.options[0].label = 'B'
    copied.disabled = True
    copied._values.append('B')
    assert original.options[0].label == 'A'
    assert not original.disabled
    assert original._values == ['A']
    assert copied.custom_id == original.custom_id


def test_deepcopy_section_rebinds_accessory_parent():
    original = ui.Section('Text', accessory=ui.Button(label='Action'))
    copied = copy.deepcopy(original)
    assert copied.accessory.parent is copied
    assert copied.accessory.custom_id != original.accessory.custom_id
    assert copied.children[0].parent is copied


@pytest.mark.asyncio
async def test_nested_row_decorator_uses_runtime_tree_not_template():
    calls = []

    class Row(ui.ActionRow):
        async def interaction_check(self, interaction):
            calls.append('row')
            return False

    class Container(ui.Container):
        row = Row()

    class View(ui.LayoutView):
        container = Container()

        @container.row.button(label='Action', custom_id='action')
        async def action(self, interaction, button):
            calls.append('callback')

    first, second = View(timeout=None), View(timeout=None)
    assert first.action.parent is first.container.row
    assert second.action.parent is second.container.row
    assert first.container.row.children == [first.action]
    assert View.container.row.children == []
    await first._scheduled_task(first.action, SimpleNamespace(data={}))
    assert calls == ['row']


def test_modal_deepcopy_preserves_custom_select_state_isolation():
    class Select(ui.Select):
        def __init__(self):
            super().__init__(options=[discord.SelectOption(label='A')])
            self.policy = {'allowed': True}

    class Modal(ui.Modal, title='Title'):
        choice = Select()

    first, second = Modal(), Modal()
    first.choice.policy['allowed'] = False
    assert second.choice.policy == {'allowed': True}
    assert Modal.choice.policy == {'allowed': True}


def test_copied_row_preserves_slotted_decorated_alias():
    class Row(ui.ActionRow):
        @ui.button(label='Action')
        async def action(self, interaction, button):
            pass

    class SlottedRow(Row):
        __slots__ = ('action',)

    original = SlottedRow()
    copied = original.copy()
    assert copied.action is copied.children[0]
    assert original.action is original.children[0]


def test_detached_decorator_parent_cannot_mutate_a_shared_template():
    row = ui.ActionRow()

    class View(ui.LayoutView):
        @row.button(label='Action')
        async def action(self, interaction, button):
            pass

    with pytest.raises(ValueError, match='parent'):
        View()
    assert row.children == []
