import * as React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { StandardIcon } from '../../../components/resources/StandardIcon';

const frontend = resolve(process.cwd(), '../dlcs/dbfox.game/frontend');
const url = (source: string) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
afterEach(cleanup);

it('opens a concrete Game after creation/selection and restores its selected subject after remount', async () => {
  const model = (await readFile(resolve(frontend, 'model.js'), 'utf8'))
    .replace('export async function listGames(', 'async function unusedListGames(')
    .replace('export async function readGame(', 'async function unusedReadGame(');
  const fixture = `
    const revision = {id:'game-1',title:'Fox',version:2};
    const document = {id:'game-1',title:'Fox',initial_scene_id:'scene-1',scenes:[{id:'scene-1',name:'Forest'}],entities:[{id:'fox-1',name:'Fox entity',scene_id:'scene-1',enabled:true,tags:[],components:[]}],behaviors:[],rules:[],variables:[],assets:[]};
    export async function listGames(){return {library_version:3,items:[revision]};}
    export async function readGame(invoke,id){await invoke('games.head',{game_id:id});return {revision,document};}
  `;
  const source = (await readFile(resolve(frontend, 'studio.js'), 'utf8'))
    .replace("'./model.js'", JSON.stringify(url(model + fixture)))
    .replace("'./forms.js'", JSON.stringify(url(await readFile(resolve(frontend, 'forms.js'), 'utf8'))))
    .replace("'./presets.js'", JSON.stringify(url(await readFile(resolve(frontend, 'presets.js'), 'utf8'))))
    .replace("'./viewport.js'", JSON.stringify(url('export const createViewport=()=>()=>null;')));
  const { createStudio } = await import(/* @vite-ignore */ url(source));
  const open = vi.fn();
  const invoke = vi.fn(async () => ({game:{id:'game-1',title:'Fox',version:2},library_version:3}));
  const status = {state:'unavailable',message:'Fixture'};
  const Studio = createStudio(React, {operations:{invoke},ui:{Tree:()=>null,Icon:StandardIcon}}, {
    registerCleanup:()=>()=>{},
    executor:{subscribe:()=>()=>{},getSnapshot:()=>status},
  }, open);
  const context = {workbenchScopeId:'scope-1',onAsk:vi.fn()};
  const libraryView = {projectId:'project-1',viewKey:'library'};
  const first = render(<Studio view={libraryView} context={context}/>);
  await screen.findByRole('button',{name:'创建游戏'});
  fireEvent.change(screen.getByRole('combobox',{name:'选择游戏'}), {target:{value:'game-1'}});
  expect(open).toHaveBeenLastCalledWith('project-1', {id:'game-1',title:'Fox',version:2});
  fireEvent.click(screen.getByRole('button',{name:'创建游戏'}));
  await vi.waitFor(()=>expect(open).toHaveBeenCalledTimes(2));
  first.unmount();
  const locatedView = {projectId:'project-1',viewKey:'game-1',target:{type:'object',object:{kind:'dbfox.game.project',id:'game-1'},authority:{kind:'dbfox.game.project',id:'game-1'},locator:'entities/fox-1'}};
  const second = render(<Studio view={locatedView} context={context}/>);
  await screen.findByRole('heading',{name:'Fox entity'});
  expect(invoke).toHaveBeenLastCalledWith('games.head',{game_id:'game-1'},expect.objectContaining({projectId:'project-1'}));
  second.unmount(); // Artifact activation unmounts the editor in the real Host.
  render(<Studio view={locatedView} context={context}/>);
  await screen.findByRole('heading',{name:'Fox entity'});
  expect((screen.getByRole('combobox',{name:'选择游戏'}) as HTMLSelectElement).value).toBe('game-1');
});
