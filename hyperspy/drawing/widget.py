# -*- coding: utf-8 -*-
# Copyright 2007-2016 The HyperSpy developers
#
# This file is part of  HyperSpy.
#
#  HyperSpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#  HyperSpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with  HyperSpy.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division

import matplotlib.pyplot as plt
import numpy as np

from utils import on_figure_window_close
from hyperspy.events import Events, Event


class WidgetBase(object):

    """Base class for interactive widgets/patches. A widget creates and
    maintains one or more matplotlib patches, and manages the interaction code
    so that the user can maniuplate it on the fly.

    This base class implements functionality witch is common to all such
    widgets, mainly the code that manages the patch, axes management, and
    sets up common events ('changed' and 'closed').

    Any inherting subclasses must implement the following methods:
        _set_patch(self)
        _on_navigate(obj, name, old, new)  # Only for widgets that can navigate

    It should also make sure to fill the 'axes' attribute as early as
    possible (but after the base class init), so that it is available when
    needed.
    """

    def __init__(self, axes_manager=None, **kwargs):
        self.axes_manager = axes_manager
        self.axes = list()
        self.ax = None
        self.picked = False
        self._size = 1.
        self.color = 'red'
        self.__is_on = True
        self.background = None
        self.patch = []
        self.cids = list()
        self.blit = True
        self.events = Events()
        self.events.changed = Event(doc="""
            Event that triggers when the widget has a significant change.

            The event triggers after the internal state of the widget has been
            updated.

            Arguments:
            ----------
                widget:
                    The widget that changed
            """, arguments=['widget'])
        self.events.closed = Event(doc="""
            Event that triggers when the widget closed.

            The event triggers after the widget has already been closed.

            Arguments:
            ----------
                widget:
                    The widget that closed
            """, arguments=['widget'])
        self._navigating = False
        super(WidgetBase, self).__init__(**kwargs)

    def is_on(self):
        """Determines if the widget is set to draw if valid (turned on).
        """
        return self.__is_on

    def set_on(self, value):
        """Change the on state of the widget. If turning off, all patches will
        be removed from the matplotlib axes and the widget will disconnect from
        all events. If turning on, the patch(es) will be added to the
        matplotlib axes, and the widget will connect to its default events.
        """
        if value is not self.is_on() and self.ax is not None:
            if value is True:
                self._add_patch_to(self.ax)
                self.connect(self.ax)
            elif value is False:
                for container in [
                        self.ax.patches,
                        self.ax.lines,
                        self.ax.artists,
                        self.ax.texts]:
                    for p in self.patch:
                        if p in container:
                            container.remove(p)
                self.disconnect(self.ax)
            try:
                self.draw_patch()
            except:  # figure does not exist
                pass
            if value is False:
                self.ax = None
        if hasattr(super(WidgetBase, self), 'set_on'):
            super(WidgetBase, self).set_on(value)
        self.__is_on = value

    def _set_patch(self):
        """Create the matplotlib patch(es), and store it in self.patch
        """
        if hasattr(super(WidgetBase, self), '_set_patch'):
            super(WidgetBase, self)._set_patch()
        # Must be provided by the subclass

    def _add_patch_to(self, ax):
        """Create and add the matplotlib patches to 'ax'
        """
        self._set_patch()
        for p in self.patch:
            ax.add_artist(p)
            p.set_animated(hasattr(ax, 'hspy_fig'))
        if hasattr(super(WidgetBase, self), '_add_patch_to'):
            super(WidgetBase, self)._add_patch_to(ax)

    def set_mpl_ax(self, ax):
        """Set the matplotlib Axes that the widget will draw to. If the widget
        on state is True, it will also add the patch to the Axes, and connect
        to its default events.
        """
        if ax is self.ax:
            return  # Do nothing
        # Disconnect from previous axes if set
        if self.ax is not None and self.is_on():
            self.disconnect(self.ax)
        self.ax = ax
        canvas = ax.figure.canvas
        if self.is_on() is True:
            self._add_patch_to(ax)
            self.connect(ax)
            if self._navigating:
                self.connect_navigate()
            canvas.draw()

    def connect(self, ax):
        """Connect to the matplotlib Axes' events.
        """
        on_figure_window_close(ax.figure, self.close)

    def connect_navigate(self):
        """Connect to the axes_manager such that changes in the widget or in
        the axes_manager are reflected in the other.
        """
        if self._navigating:
            self.disconnect_navigate()
        self.axes_manager.events.indices_changed.connect(self._on_navigate)
        self._on_navigate(self.axes_manager)    # Update our position
        self._navigating = True

    def disconnect_navigate(self):
        """Disconnect a previous naivgation connection.
        """
        self.axes_manager.events.indices_changed.disconnect(self._on_navigate)
        self._navigating = False

    def _on_navigate(self, axes_manager):
        """Callback for axes_manager's change notification.
        """
        pass    # Implement in subclass!

    def disconnect(self, ax):
        """Disconnect from all events (both matplotlib and navigation).
        """
        for cid in self.cids:
            try:
                ax.figure.canvas.mpl_disconnect(cid)
            except:
                pass
        if self._navigating:
            self.disconnect_navigate()

    def close(self, window=None):
        """Set the on state to off (removes patch and disconnects), and trigger
        events.closed.
        """
        self.set_on(False)
        self.events.closed.trigger(self)

    def draw_patch(self, *args):
        """Update the patch drawing.
        """
        if hasattr(self.ax, 'hspy_fig'):
            self.ax.hspy_fig._draw_animated()
        else:
            self.ax.figure.canvas.draw_idle()

    def _v2i(self, axis, v):
        """Wrapped version of DataAxis.value2index, which bounds the index
        inbetween axis.low_index and axis.high_index+1, and does not raise a
        ValueError.
        """
        try:
            return axis.value2index(v)
        except ValueError:
            if v > axis.high_value:
                return axis.high_index + 1
            elif v < axis.low_value:
                return axis.low_index
            else:
                raise

    def _i2v(self, axis, i):
        """Wrapped version of DataAxis.index2value, which bounds the value
        inbetween axis.low_value and axis.high_value+axis.scale, and does not
        raise a ValueError.
        """
        try:
            return axis.index2value(i)
        except ValueError:
            if i > axis.high_index:
                return axis.high_value + axis.scale
            elif i < axis.low_index:
                return axis.low_value
            else:
                raise


class DraggableWidgetBase(WidgetBase):

    """Adds the `position` and `indices` properties, and adds a framework for
    letting the user drag the patch around. Also adds the `moved` event.

    The default behavior is that `position` snaps to the values corresponding
    to the values of the axes grid (i.e. no subpixel values). This behavior
    can be controlled by the property `snap_position`.

    Any inheritors must override these methods:
        _onmousemove(self, event)
        _update_patch_position(self)
        _set_patch(self)
    """

    def __init__(self, axes_manager, **kwargs):
        super(DraggableWidgetBase, self).__init__(axes_manager, **kwargs)
        self.events.moved = Event(doc="""
            Event that triggers when the widget was moved.

            The event triggers after the internal state of the widget has been
            updated. This event does not differentiate on how the position of
            the widget was changed, so it is the responsibility of the user
            to suppress events as neccessary to avoid closed loops etc.

            Arguments:
            ----------
                position:
                widget:
                    The widget that was moved.
            """, arguments=['widget'])
        self._snap_position = True

        # Set default axes
        if self.axes_manager is not None:
            if self.axes_manager.navigation_dimension > 0:
                self.axes = self.axes_manager.navigation_axes[0:1]
            else:
                self.axes = self.axes_manager.signal_axes[0:1]
            self._pos = np.array([self.axes[0].low_value])
        else:
            self._pos = np.array([0.])

    def _get_indices(self):
        """Returns a tuple with the position (indices).
        """
        idx = []
        pos = self.position
        for i in xrange(len(self.axes)):
            idx.append(self.axes[i].value2index(pos[i]))
        return tuple(idx)

    def _set_indices(self, value):
        """Sets the position of the widget (by indices). The dimensions should
        correspond to that of the 'axes' attribute. Calls _pos_changed if the
        value has changed, which is then responsible for triggering any
        relevant events.
        """
        if np.ndim(value) == 0 and len(self.axes) == 1:
            self.position = [self.axes[0].index2value(value)]
        elif len(self.axes) != len(value):
            raise ValueError()
        else:
            p = []
            for i in xrange(len(self.axes)):
                p.append(self.axes[i].index2value(value[i]))
            self.position = p

    indices = property(lambda s: s._get_indices(),
                       lambda s, v: s._set_indices(v))

    def _pos_changed(self):
        """Call when the position of the widget has changed. It triggers the
        relevant events, and updates the patch position.
        """
        if self._navigating:
            with self.axes_manager.events.indices_changed.suppress_callback(
                    self._on_navigate):
                for i in xrange(len(self.axes)):
                    self.axes[i].value = self.position[i]
        self.events.moved.trigger(self)
        self.events.changed.trigger(self)
        self._update_patch_position()

    def _validate_pos(self, pos):
        """Validates the passed position. Depending on the position and the
        implementation, this can either fire a ValueError, or return a modified
        position that has valid values. Or simply return the unmodified
        position if everything is ok.

        This default implementation raises a ValueError if the position is out
        of bounds (as defiend by the axes).
        """
        if len(pos) != len(self.axes):
            raise ValueError()
        for i in xrange(len(pos)):
            if not (self.axes[i].low_value <= pos[i] <=
                    self.axes[i].high_value):
                raise ValueError()
        if self.snap_position:
            pos = self._do_snap_position(pos)
        return pos

    def _get_position(self):
        """Providies the position of the widget (by values) in a tuple.
        """
        return tuple(
            self._pos.tolist())  # Don't pass reference, and make it clear

    def _set_position(self, position):
        """Sets the position of the widget (by values). The dimensions should
        correspond to that of the 'axes' attribute. Calls _pos_changed if the
        value has changed, which is then responsible for triggering any
        relevant events.
        """
        position = self._validate_pos(position)
        if np.any(self._pos != position):
            self._pos = np.array(position)
            self._pos_changed()

    position = property(lambda s: s._get_position(),
                        lambda s, v: s._set_position(v))

    def _do_snap_position(self, value=None):
        """Snaps position to axes grid. Returns True if postion was adjusted,
        otherwise False.
        """
        value = np.array(value) if value is not None else self._pos
        for i, ax in enumerate(self.axes):
            value[i] = ax.index2value(ax.value2index(value[i]))
        return value

    def _set_snap_position(self, value):
        self._snap_position = value
        if value:
            snap_value = self._do_snap_position(self._pos)
            if np.any(self._pos != snap_value):
                self._pos = snap_value
                self._pos_changed()

    snap_position = property(lambda s: s._snap_position,
                             lambda s, v: s._set_snap_position(v))

    def connect(self, ax):
        super(DraggableWidgetBase, self).connect(ax)
        canvas = ax.figure.canvas
        self.cids.append(
            canvas.mpl_connect('motion_notify_event', self._onmousemove))
        self.cids.append(canvas.mpl_connect('pick_event', self.onpick))
        self.cids.append(canvas.mpl_connect(
            'button_release_event', self.button_release))

    def _on_navigate(self, axes_manager):
        if axes_manager is self.axes_manager:
            p = list(self.position)
            for i, a in enumerate(self.axes):
                p[i] = a.value
            self.position = p    # Use property to trigger events

    def onpick(self, event):
        # Callback for MPL pick event
        self.picked = (event.artist in self.patch)
        if hasattr(super(DraggableWidgetBase, self), 'onpick'):
            super(DraggableWidgetBase, self).onpick(event)

    def _onmousemove(self, event):
        """Callback for mouse movement. For dragging, the implementor would
        normally check that the widget is picked, and that the event.inaxes
        Axes equals self.ax.
        """
        # This method must be provided by the subclass
        pass

    def _update_patch_position(self):
        """Updates the position of the patch on the plot.
        """
        # This method must be provided by the subclass
        pass

    def _update_patch_geometry(self):
        """Updates all geometry of the patch on the plot.
        """
        self._update_patch_position()

    def button_release(self, event):
        """whenever a mouse button is released"""
        if event.button != 1:
            return
        if self.picked is True:
            self.picked = False


class ResizableDraggableWidgetBase(DraggableWidgetBase):

    """Adds the `size` property and get_size_in_axes method, and adds a
    framework for letting the user resize the patch, including resizing by
    key strokes ('+', '-'). Also adds the 'resized' event.

    Utility functions for resizing are implemented by `increase_size` and
    `decrease_size`, which will in-/decrement the size by 1. Other utility
    functions include `get_centre` and `get_centre_indices` which returns the
    center position, and the internal _apply_changes which helps make sure that
    only one 'changed' event is fired for a combined move and resize.

    Any inheritors must override these methods:
        _update_patch_position(self)
        _update_patch_size(self)
        _update_patch_geometry(self)
        _set_patch(self)
    """

    def __init__(self, axes_manager, **kwargs):
        super(ResizableDraggableWidgetBase, self).__init__(
            axes_manager, **kwargs)
        if self.axes:
            self._size = np.array([self.axes[0].scale])
        else:
            self._size = np.array([1])
        self.size_step = 1      # = one step in index space
        self._snap_size = True
        self.events.resized = Event(doc="""
            Event that triggers when the widget was resized.

            The event triggers after the internal state of the widget has been
            updated. This event does not differentiate on how the size of
            the widget was changed, so it is the responsibility of the user
            to suppress events as neccessary to avoid closed loops etc.

            Arguments:
            ----------
                widget:
                    The widget that was resized.
            """, arguments=['widget'])

    def _get_size(self):
        """Getter for 'size' property. Returns the size as a tuple (to prevent
        unintended in-place changes).
        """
        return tuple(self._size.tolist())

    def _set_size(self, value):
        """Setter for the 'size' property. Calls _size_changed to handle size
        change, if the value has changed.
        """
        value = np.minimum(value, [ax.size * ax.scale for ax in self.axes])
        value = np.maximum(value,
                           self.size_step * [ax.scale for ax in self.axes])
        if self.snap_size:
            value = self._do_snap_size(value)
        if np.any(self._size != value):
            self._size = value
            self._size_changed()

    size = property(lambda s: s._get_size(), lambda s, v: s._set_size(v))

    def _do_snap_size(self, value=None):
        value = np.array(value) if value is not None else self._size
        for i, ax in enumerate(self.axes):
            value[i] = round(value[i] / ax.scale) * ax.scale
        return value

    def _set_snap_size(self, value):
        self._snap_size = value
        if value:
            snap_value = self._do_snap_size(self._size)
            if np.any(self._size != snap_value):
                self._size = snap_value
                self._size_changed()

    snap_size = property(lambda s: s._snap_size,
                         lambda s, v: s._set_snap_size(v))

    def _set_snap_all(self, value):
        # Snap position first, as snapped size can depend on position.
        self.snap_position = value
        self.snap_size = value

    snap_all = property(lambda s: s.snap_size and s.snap_position,
                        lambda s, v: s._set_snap_all(v))

    def increase_size(self):
        """Increment all sizes by 1. Applied via 'size' property.
        """
        self.size = np.array(self.size) + \
            self.size_step * np.array([a.scale for a in self.axes])

    def decrease_size(self):
        """Decrement all sizes by 1. Applied via 'size' property.
        """
        self.size = np.array(self.size) - \
            self.size_step * np.array([a.scale for a in self.axes])

    def _size_changed(self):
        """Triggers resize and changed events, and updates the patch.
        """
        self.events.resized.trigger(self)
        self.events.changed.trigger(self)
        self._update_patch_size()

    def get_size_in_indices(self):
        """Gets the size property converted to the index space (via 'axes'
        attribute).
        """
        s = list()
        for i in xrange(len(self.axes)):
            s.append(int(self._size[i] / self.axes[i].scale))
        return np.array(s)

    def set_size_in_indices(self, value):
        """Sets the size property converted to the index space (via 'axes'
        attribute).
        """
        s = list()
        for i in xrange(len(self.axes)):
            s.append(int(value[i] * self.axes[i].scale))
        self.size = s   # Use property to get full processing

    def get_centre(self):
        """Get's the center indices. The default implementation is simply the
        position + half the size in axes space, which should work for any
        symmetric widget, but more advanced widgets will need to decide whether
        to return the center of gravity or the geometrical center of the
        bounds.
        """
        return self._pos + self._size() / 2.0

    def get_centre_index(self):
        """Get's the center position (in index space). The default
        implementation is simply the indices + half the size, which should
        work for any symmetric widget, but more advanced widgets will need to
        decide whether to return the center of gravity or the geometrical
        center of the bounds.
        """
        return self.indices + self.get_size_in_indices() / 2.0

    def _update_patch_size(self):
        """Updates the size of the patch on the plot.
        """
        # This method must be provided by the subclass
        pass

    def _update_patch_geometry(self):
        """Updates all geometry of the patch on the plot.
        """
        # This method must be provided by the subclass
        pass

    def on_key_press(self, event):
        if event.key == "+":
            self.increase_size()
        if event.key == "-":
            self.decrease_size()

    def connect(self, ax):
        super(ResizableDraggableWidgetBase, self).connect(ax)
        canvas = ax.figure.canvas
        self.cids.append(canvas.mpl_connect('key_press_event',
                                            self.on_key_press))

    def _apply_changes(self, old_size, old_position):
        """Evalutes whether the widget has been moved/resized, and triggers
        the correct events and updates the patch geometry. This function has
        the advantage that the geometry is updated only once, preventing
        flickering, and the 'changed' event only fires once.
        """
        moved = self.position != old_position
        resized = self.size != old_size
        if moved:
            if self._navigating:
                e = self.axes_manager.events.indices_changed
                with e.suppress_callback(self._on_navigate):
                    for i in xrange(len(self.axes)):
                        self.axes[i].index = self.indices[i]
            self.events.moved.trigger(self)
        if resized:
            self.events.resized.trigger(self)
        if moved or resized:
            self.events.changed.trigger(self)
            if moved and resized:
                self._update_patch_geometry()
            elif moved:
                self._update_patch_position()
            else:
                self._update_patch_size()


class Widget2DBase(ResizableDraggableWidgetBase):

    """A base class for 2D widgets. It sets the right dimensions for size and
    position, adds the 'border_thickness' attribute and initalizes the 'axes'
    attribute to the first two navigation axes if possible, if not, the two
    first signal_axes are used. Other than that it mainly supplies common
    utility functions for inheritors, and implements required functions for
    ResizableDraggableWidgetBase.

    The implementation for ResizableDraggableWidgetBase methods all assume that
    a Rectangle patch will be used, centered on position. If not, the
    inheriting class will have to override those as applicable.
    """

    def __init__(self, axes_manager, **kwargs):
        super(Widget2DBase, self).__init__(axes_manager, **kwargs)
        self.border_thickness = 2

        # Set default axes
        if self.axes_manager is not None:
            if self.axes_manager.navigation_dimension > 1:
                self.axes = self.axes_manager.navigation_axes[0:2]
            elif self.axes_manager.signal_dimension > 1:
                self.axes = self.axes_manager.signal_axes[0:2]
            elif len(self.axes_manager.shape) > 1:
                self.axes = (self.axes_manager.signal_axes +
                             self.axes_manager.navigation_axes)
            else:
                raise ValueError("2D widget needs at least two axes!")
            self._pos = np.array([self.axes[0].offset, self.axes[1].offset])
            self._size = np.array([self.axes[0].scale, self.axes[1].scale])
        else:
            self._pos = np.array([0, 0])
            self._size = np.array([1, 1])

    def _get_patch_xy(self):
        """Returns the xy position of the widget. In this default
        implementation, the widget is centered on the position.
        """
        return np.array(self.position) - np.array(self.size) / 2.

    def _get_patch_bounds(self):
        """Returns the bounds of the patch in the form of a tuple in the order
        left, top, width, height. In matplotlib, 'bottom' is used instead of
        'top' as the naming assumes an upwards pointing y-axis, meaning the
        lowest value corresponds to bottom. However, our widgets will normally
        only go on images (which has an inverted y-axis in MPL by default), so
        we define the lowest value to be termed 'top'.
        """
        xy = self._get_patch_xy()
        xs, ys = self.size
        return (xy[0], xy[1], xs, ys)        # x,y,w,h

    def _update_patch_position(self):
        if self.is_on() and self.patch:
            self.patch[0].set_xy(self._get_patch_xy())
            self.draw_patch()

    def _update_patch_size(self):
        self._update_patch_geometry()

    def _update_patch_geometry(self):
        if self.is_on() and self.patch:
            self.patch[0].set_bounds(*self._get_patch_bounds())
            self.draw_patch()

