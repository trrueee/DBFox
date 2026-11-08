import { useEffect } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ConversationWorkspaceLayout, initialDockWidth } from '../ConversationWorkspaceLayout';

afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();});

it('balances the initial Dock against the conversation and preserves an explicit resize', () => {
  expect(initialDockWidth(1176, 600, 38)).toBeCloseTo(446.88);
  expect(initialDockWidth(1176, 680, 28)).toBe(340);
  expect(initialDockWidth(1600, 480, 38)).toBe(480);
  expect(initialDockWidth(1176, 600, 38, 560)).toBe(560);
  expect(initialDockWidth(904, 680, 38, 680)).toBe(376);
  expect(initialDockWidth(696, 680, 38)).toBe(696);
});
it('uses actual stage width and retains mounted drafts across compact/split transitions', () => {
  let width = 1176;
  const observers = new Set<() => void>();
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0,0,width,860));
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) { observers.add(() => callback([], this as unknown as ResizeObserver)); }
    observe() {} unobserve() {} disconnect() {}
  });
  const mount = vi.fn(), unmount = vi.fn();
  function Draft() { useEffect(() => {mount(); return unmount;}, []); return <input aria-label="DLC draft" defaultValue="original"/>; }
  const props = {conversation:<input aria-label="Conversation draft"/>,dock:<Draft/>};
  const view = render(<ConversationWorkspaceLayout {...props} dockOpen/>);
  fireEvent.change(screen.getByRole('textbox',{name:'DLC draft'}),{target:{value:'unsaved'}});
  expect(screen.getByRole('separator',{name:'调整工作区宽度'})).toBeTruthy();
  act(()=>{width=696; observers.forEach(callback=>callback());});
  expect(view.container.querySelector('[data-compact="true"]')).toBeTruthy();
  expect(screen.queryByRole('textbox',{name:'Conversation draft'})).toBeNull();
  expect(screen.queryByRole('separator')).toBeNull();
  expect((screen.getByRole('textbox',{name:'DLC draft'}) as HTMLInputElement).value).toBe('unsaved');
  act(()=>{width=904; observers.forEach(callback=>callback());}); // navigation collapse at the same outer size
  expect(view.container.querySelector('[data-compact="true"]')).toBeNull();
  expect(screen.getByRole('separator')).toBeTruthy();
  expect(mount).toHaveBeenCalledTimes(1); expect(unmount).not.toHaveBeenCalled();
  act(()=>{width=696; observers.forEach(callback=>callback());});
  view.rerender(<ConversationWorkspaceLayout {...props} dockOpen={false}/>);
  expect(screen.getByRole('textbox',{name:'Conversation draft'})).toBeTruthy();
  view.rerender(<ConversationWorkspaceLayout {...props} dockOpen/>);
  expect(screen.queryByRole('textbox',{name:'Conversation draft'})).toBeNull();
});

it.each([true, false])('applies compact layout on first measurement with dockOpen=%s', (dockOpen) => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => new DOMRect(0,0,696,860));
  const view = render(<ConversationWorkspaceLayout dockOpen={dockOpen} conversation={<button>Conversation control</button>} dock={<button>Dock control</button>}/>);
  expect(view.container.querySelector('[data-compact="true"]')).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Conversation control'}) !== null).toBe(!dockOpen);
  expect(screen.getByRole('button',{name:'Dock control'})).toBeTruthy();
  expect(screen.queryByRole('separator')).toBeNull();
});
