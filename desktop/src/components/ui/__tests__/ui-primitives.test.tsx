import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Button } from "../button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSearch,
} from "../command";
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuTrigger } from "../context-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../dropdown-menu";
import { Input } from "../input";
import { Panel, PanelBody, PanelDescription, PanelFooter, PanelHeader, PanelTitle } from "../panel";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "../hover-card";
import { Popover, PopoverContent, PopoverTrigger } from "../popover";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "../resizable";
import { Select } from "../select";
import { EmptyState, ErrorState, LoadingState } from "../state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../tabs";
import { ScrollArea } from "../scroll-area";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../tooltip";
import { Toolbar, ToolbarGroup, ToolbarTitle } from "../toolbar";
import {
  Button as IndexedButton,
  Command as IndexedCommand,
  CommandEmpty as IndexedCommandEmpty,
  CommandGroup as IndexedCommandGroup,
  CommandInput as IndexedCommandInput,
  CommandItem as IndexedCommandItem,
  CommandList as IndexedCommandList,
  CommandSearch as IndexedCommandSearch,
  ContextMenu as IndexedContextMenu,
  ContextMenuContent as IndexedContextMenuContent,
  ContextMenuItem as IndexedContextMenuItem,
  ContextMenuSeparator as IndexedContextMenuSeparator,
  ContextMenuTrigger as IndexedContextMenuTrigger,
  Dialog as IndexedDialog,
  DialogContent as IndexedDialogContent,
  DialogDescription as IndexedDialogDescription,
  DialogFooter as IndexedDialogFooter,
  DialogHeader as IndexedDialogHeader,
  DialogTitle as IndexedDialogTitle,
  DropdownMenu as IndexedDropdownMenu,
  DropdownMenuContent as IndexedDropdownMenuContent,
  DropdownMenuItem as IndexedDropdownMenuItem,
  DropdownMenuSeparator as IndexedDropdownMenuSeparator,
  DropdownMenuTrigger as IndexedDropdownMenuTrigger,
  EmptyState as IndexedEmptyState,
  Input as IndexedInput,
  Panel as IndexedPanel,
  PanelBody as IndexedPanelBody,
  PanelHeader as IndexedPanelHeader,
  PanelTitle as IndexedPanelTitle,
  HoverCard as IndexedHoverCard,
  HoverCardContent as IndexedHoverCardContent,
  HoverCardTrigger as IndexedHoverCardTrigger,
  Popover as IndexedPopover,
  PopoverContent as IndexedPopoverContent,
  PopoverTrigger as IndexedPopoverTrigger,
  ResizableHandle as IndexedResizableHandle,
  ResizablePanel as IndexedResizablePanel,
  ResizablePanelGroup as IndexedResizablePanelGroup,
  Select as IndexedSelect,
  ScrollArea as IndexedScrollArea,
  Tabs as IndexedTabs,
  TabsContent as IndexedTabsContent,
  TabsList as IndexedTabsList,
  TabsTrigger as IndexedTabsTrigger,
  Tooltip as IndexedTooltip,
  TooltipContent as IndexedTooltipContent,
  TooltipProvider as IndexedTooltipProvider,
  TooltipTrigger as IndexedTooltipTrigger,
  Toolbar as IndexedToolbar,
  ToolbarGroup as IndexedToolbarGroup,
  ToolbarTitle as IndexedToolbarTitle,
} from "../index";

describe("ui primitives", () => {
  beforeEach(() => cleanup());

  it("renders a panel with stable title, description, body, and footer regions", () => {
    render(
      <Panel aria-label="数据源详情">
        <PanelHeader>
          <PanelTitle>连接详情</PanelTitle>
          <PanelDescription>生产只读连接</PanelDescription>
        </PanelHeader>
        <PanelBody>schema 已同步</PanelBody>
        <PanelFooter>最后检查 42ms</PanelFooter>
      </Panel>
    );

    expect(screen.getByRole("region", { name: "数据源详情" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "连接详情" })).toBeTruthy();
    expect(screen.getByText("生产只读连接")).toBeTruthy();
    expect(screen.getByText("schema 已同步")).toBeTruthy();
    expect(screen.getByText("最后检查 42ms")).toBeTruthy();
  });

  it("provides toolbar, form control, and action states without page-specific classes", () => {
    const onClick = vi.fn();

    render(
      <Toolbar aria-label="SQL 工具栏">
        <ToolbarTitle>SQL Console</ToolbarTitle>
        <ToolbarGroup>
          <Input aria-label="过滤" placeholder="过滤对象" />
          <Select aria-label="环境" defaultValue="dev">
            <option value="dev">Dev</option>
            <option value="prod">Prod</option>
          </Select>
          <Button onClick={onClick}>执行</Button>
          <Button disabled>取消</Button>
        </ToolbarGroup>
      </Toolbar>
    );

    expect(screen.getByRole("toolbar", { name: "SQL 工具栏" })).toBeTruthy();
    expect(screen.getByText("SQL Console")).toBeTruthy();
    expect(screen.getByLabelText("过滤").getAttribute("placeholder")).toBe("过滤对象");
    expect(screen.getByRole("combobox", { name: "环境" }).className).toContain("dbfox-select-trigger");
    expect(screen.getByRole("combobox", { name: "环境" }).textContent).toContain("Dev");
    chooseSelectOption("环境", "Prod");
    expect(screen.getByRole("combobox", { name: "环境" }).textContent).toContain("Prod");
    fireEvent.click(screen.getByRole("button", { name: "执行" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect((screen.getByRole("button", { name: "取消" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("standardizes empty, error, and loading states", () => {
    const onRetry = vi.fn();

    render(
      <>
        <EmptyState title="暂无表" description="同步 schema 后会显示表结构。" action={<Button>同步</Button>} />
        <ErrorState title="加载失败" description="连接已断开" onRetry={onRetry} />
        <LoadingState label="正在加载列信息" />
      </>
    );

    expect(screen.getByRole("heading", { name: "暂无表" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "同步" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("加载失败");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status").textContent).toContain("正在加载列信息");
  });

  it("wraps Radix Popover as a DBFox primitive", () => {
    render(
      <Popover>
        <PopoverTrigger asChild>
          <Button>打开筛选</Button>
        </PopoverTrigger>
        <PopoverContent aria-label="筛选设置">筛选内容</PopoverContent>
      </Popover>
    );

    fireEvent.click(screen.getByRole("button", { name: "打开筛选" }));

    expect(document.querySelector(".dbfox-popover-content")).toBeTruthy();
    expect(document.querySelector(".dbfox-popover-arrow")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "筛选设置" }).textContent).toContain("筛选内容");
  });

  it("wraps react-resizable-panels as a DBFox primitive", () => {
    render(
      <ResizablePanelGroup direction="horizontal" className="test-resizable-group">
        <ResizablePanel defaultSize={30} minSize={20}>
          <div>Sidebar panel</div>
        </ResizablePanel>
        <ResizableHandle aria-label="Resize sidebar" />
        <ResizablePanel defaultSize={70}>
          <div>Main panel</div>
        </ResizablePanel>
      </ResizablePanelGroup>,
    );

    expect(document.querySelector(".dbfox-resizable-panel-group")).toBeTruthy();
    expect(document.querySelector(".test-resizable-group")).toBeTruthy();
    expect(document.querySelectorAll(".dbfox-resizable-panel")).toHaveLength(2);
    expect(screen.getByRole("separator", { name: "Resize sidebar" }).className).toContain("dbfox-resizable-handle");
    expect(screen.getByText("Sidebar panel")).toBeTruthy();
    expect(screen.getByText("Main panel")).toBeTruthy();
  });

  it("wraps cmdk as a DBFox Command primitive", () => {
    const onSelect = vi.fn();

    render(
      <Command label="Command test">
        <CommandSearch>
          <CommandInput placeholder="Search commands" />
        </CommandSearch>
        <CommandList>
          <CommandEmpty>No commands</CommandEmpty>
          <CommandGroup heading={<span className="dbfox-command-category">Actions</span>}>
            <CommandItem value="open" onSelect={onSelect}>
              Open command
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>,
    );

    expect(document.querySelector(".dbfox-command-panel")).toBeTruthy();
    expect(document.querySelector(".dbfox-command-search")).toBeTruthy();
    expect(screen.getByPlaceholderText("Search commands").className).toContain("dbfox-command-input");
    expect(screen.getByText("Open command").className).toContain("dbfox-command-item");

    fireEvent.click(screen.getByText("Open command"));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("wraps Radix Dialog as a DBFox primitive", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Connection settings</DialogTitle>
            <DialogDescription>Configure the active datasource.</DialogDescription>
          </DialogHeader>
          <div>Dialog body</div>
          <DialogFooter>
            <Button>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );

    expect(document.querySelector(".dbfox-dialog-overlay")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Connection settings" }).className).toContain("dbfox-dialog-content");
    expect(document.querySelector(".dbfox-dialog-header")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Connection settings" }).className).toContain("dbfox-dialog-title");
    expect(screen.getByText("Configure the active datasource.").className).toContain("dbfox-dialog-description");
    expect(document.querySelector(".dbfox-dialog-footer")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close" }).className).toContain("dbfox-dialog-close");
  });

  it("wraps Radix HoverCard as a DBFox primitive", () => {
    render(
      <HoverCard open>
        <HoverCardTrigger asChild>
          <Button>Preview cell</Button>
        </HoverCardTrigger>
        <HoverCardContent aria-label="Cell preview">Preview body</HoverCardContent>
      </HoverCard>
    );

    expect(document.querySelector(".dbfox-hover-card-content")).toBeTruthy();
    expect(document.querySelector(".dbfox-hover-card-arrow")).toBeTruthy();
    expect(screen.getByText("Preview body")).toBeTruthy();
  });

  it("wraps Radix DropdownMenu as a DBFox primitive", () => {
    const onSelect = vi.fn();

    render(
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button>Column actions</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent aria-label="Column menu">
          <DropdownMenuItem onSelect={onSelect}>Sort ascending</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem>Hide column</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "Column actions" }), { button: 0, ctrlKey: false });
    expect(screen.getByRole("menu").className).toContain("dbfox-dropdown-menu-content");
    expect(screen.getByRole("menuitem", { name: "Sort ascending" }).className).toContain("dbfox-dropdown-menu-item");
    expect(document.querySelector(".dbfox-dropdown-menu-separator")).toBeTruthy();

    fireEvent.click(screen.getByRole("menuitem", { name: "Sort ascending" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("wraps Radix ContextMenu as a DBFox primitive", () => {
    const onSelect = vi.fn();

    render(
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <button type="button">Cell trigger</button>
        </ContextMenuTrigger>
        <ContextMenuContent aria-label="Cell menu">
          <ContextMenuItem onSelect={onSelect}>Copy cell</ContextMenuItem>
          <ContextMenuSeparator />
          <ContextMenuItem>Copy row</ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: "Cell trigger" }));
    expect(screen.getByRole("menu").className).toContain("dbfox-context-menu-content");
    expect(screen.getByRole("menuitem", { name: "Copy cell" }).className).toContain("dbfox-context-menu-item");
    expect(document.querySelector(".dbfox-context-menu-separator")).toBeTruthy();

    fireEvent.click(screen.getByRole("menuitem", { name: "Copy cell" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("wraps Radix Tabs as a DBFox primitive", () => {
    render(
      <Tabs defaultValue="one">
        <TabsList aria-label="Workspace tabs">
          <TabsTrigger value="one">One</TabsTrigger>
          <TabsTrigger value="two">Two</TabsTrigger>
        </TabsList>
        <TabsContent value="one">First panel</TabsContent>
        <TabsContent value="two">Second panel</TabsContent>
      </Tabs>,
    );

    expect(screen.getByRole("tablist", { name: "Workspace tabs" }).className).toContain("dbfox-tabs-list");
    expect(screen.getByRole("tab", { name: "One" }).className).toContain("dbfox-tabs-trigger");
    expect(screen.getByRole("tab", { name: "One" }).getAttribute("data-state")).toBe("active");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Two" }), { button: 0, ctrlKey: false });
    expect(screen.getByRole("tab", { name: "Two" }).getAttribute("data-state")).toBe("active");
    expect(screen.getByText("Second panel").className).toContain("dbfox-tabs-content");
    expect(screen.getByText("Second panel")).toBeTruthy();
  });

  it("wraps Radix ScrollArea as a DBFox primitive", () => {
    render(
      <ScrollArea className="test-scroll-area">
        <div>Scrollable schema tree</div>
      </ScrollArea>,
    );

    expect(document.querySelector(".dbfox-scroll-area")).toBeTruthy();
    expect(document.querySelector(".dbfox-scroll-area-viewport")?.textContent).toContain("Scrollable schema tree");
    expect(document.querySelector(".dbfox-scroll-area-scrollbar")).toBeTruthy();
  });

  it("wraps Radix Tooltip as a DBFox primitive", () => {
    render(
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger asChild>
            <Button aria-label="刷新表结构">刷新</Button>
          </TooltipTrigger>
          <TooltipContent>重新读取表结构</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );

    expect(document.querySelector(".dbfox-tooltip-content")).toBeTruthy();
    expect(screen.getByRole("tooltip").textContent).toContain("重新读取表结构");
  });


  it("exposes primitives through the ui entrypoint", () => {
    render(
      <IndexedPanel aria-label="Indexed workspace">
        <IndexedPanelHeader>
          <IndexedPanelTitle>Indexed Panel</IndexedPanelTitle>
        </IndexedPanelHeader>
        <IndexedPanelBody>
          <IndexedToolbar aria-label="Indexed toolbar">
            <IndexedToolbarTitle>Controls</IndexedToolbarTitle>
            <IndexedToolbarGroup>
              <IndexedInput aria-label="Filter" />
              <IndexedSelect aria-label="Mode" defaultValue="compact">
                <option value="compact">Compact</option>
                <option value="wide">Wide</option>
              </IndexedSelect>
              <IndexedButton>Apply</IndexedButton>
            </IndexedToolbarGroup>
          </IndexedToolbar>
          <IndexedCommand label="Indexed command">
            <IndexedCommandSearch>
              <IndexedCommandInput placeholder="Indexed command input" />
            </IndexedCommandSearch>
            <IndexedCommandList>
              <IndexedCommandEmpty>No indexed commands</IndexedCommandEmpty>
              <IndexedCommandGroup heading="Indexed actions">
                <IndexedCommandItem>Indexed command item</IndexedCommandItem>
              </IndexedCommandGroup>
            </IndexedCommandList>
          </IndexedCommand>
          <IndexedPopover>
            <IndexedPopoverTrigger asChild>
              <IndexedButton>Indexed popover</IndexedButton>
            </IndexedPopoverTrigger>
            <IndexedPopoverContent>Popover body</IndexedPopoverContent>
          </IndexedPopover>
          <IndexedResizablePanelGroup direction="horizontal">
            <IndexedResizablePanel defaultSize={35}>Indexed left</IndexedResizablePanel>
            <IndexedResizableHandle aria-label="Indexed resize" />
            <IndexedResizablePanel defaultSize={65}>Indexed right</IndexedResizablePanel>
          </IndexedResizablePanelGroup>
          <IndexedDialog open modal={false}>
            <IndexedDialogContent>
              <IndexedDialogHeader>
                <IndexedDialogTitle>Indexed dialog</IndexedDialogTitle>
                <IndexedDialogDescription>Dialog body</IndexedDialogDescription>
              </IndexedDialogHeader>
              <IndexedDialogFooter>
                <IndexedButton>OK</IndexedButton>
              </IndexedDialogFooter>
            </IndexedDialogContent>
          </IndexedDialog>
          <IndexedHoverCard open>
            <IndexedHoverCardTrigger asChild>
              <IndexedButton>Indexed hover</IndexedButton>
            </IndexedHoverCardTrigger>
            <IndexedHoverCardContent>Hover body</IndexedHoverCardContent>
          </IndexedHoverCard>
          <IndexedDropdownMenu>
            <IndexedDropdownMenuTrigger asChild>
              <IndexedButton>Indexed dropdown</IndexedButton>
            </IndexedDropdownMenuTrigger>
            <IndexedDropdownMenuContent>
              <IndexedDropdownMenuItem>Dropdown body</IndexedDropdownMenuItem>
              <IndexedDropdownMenuSeparator />
            </IndexedDropdownMenuContent>
          </IndexedDropdownMenu>
          <IndexedContextMenu>
            <IndexedContextMenuTrigger asChild>
              <span>Indexed context</span>
            </IndexedContextMenuTrigger>
            <IndexedContextMenuContent>
              <IndexedContextMenuItem>Context body</IndexedContextMenuItem>
              <IndexedContextMenuSeparator />
            </IndexedContextMenuContent>
          </IndexedContextMenu>
          <IndexedTabs defaultValue="workspace">
            <IndexedTabsList aria-label="Indexed tabs">
              <IndexedTabsTrigger value="workspace">Workspace</IndexedTabsTrigger>
            </IndexedTabsList>
            <IndexedTabsContent value="workspace">Workspace body</IndexedTabsContent>
          </IndexedTabs>
          <IndexedScrollArea>
            <span>Indexed scroll body</span>
          </IndexedScrollArea>
          <IndexedTooltipProvider>
            <IndexedTooltip open>
              <IndexedTooltipTrigger asChild>
                <IndexedButton>Indexed tooltip</IndexedButton>
              </IndexedTooltipTrigger>
              <IndexedTooltipContent>Tooltip body</IndexedTooltipContent>
            </IndexedTooltip>
          </IndexedTooltipProvider>
          <IndexedEmptyState title="No rows" description="Run a query to see data." />
        </IndexedPanelBody>
      </IndexedPanel>
    );

    expect(screen.getByRole("region", { name: "Indexed workspace" })).toBeTruthy();
    expect(screen.getByRole("toolbar", { name: "Indexed toolbar" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Workspace" })).toBeTruthy();
    expect(screen.getByRole("separator", { name: "Indexed resize" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply" })).toBeTruthy();
    expect(screen.getByPlaceholderText("Indexed command input")).toBeTruthy();
    expect(screen.getByRole("tooltip").textContent).toContain("Tooltip body");
    expect(screen.getByText("No rows")).toBeTruthy();
  });
});

function chooseSelectOption(label: string, optionName: string) {
  fireEvent.pointerDown(screen.getByRole("combobox", { name: label }), {
    button: 0,
    ctrlKey: false,
    pointerId: 1,
    pointerType: "mouse",
  });
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}
