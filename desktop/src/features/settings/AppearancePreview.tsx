import { Folder, Plus } from "lucide-react";
import { Sidebar, SidebarContent, SidebarHeader, SidebarNavRow } from "../../components/ui";
import { ReferenceCard } from "../../components/resources/ReferenceCard";
import { UnifiedComposer } from "../../components/agent/UnifiedComposer";

/** Real presentation primitives, deliberately inert: previewing never creates a task. */
export function AppearancePreview() {
  return <aside className="appearance-live-preview" aria-label="当前外观预览">
    <div className="appearance-live-preview__label"><span>效果预览</span><small>随设置即时更新</small></div>
    <div className="appearance-workspace-preview" inert aria-hidden="true">
      <Sidebar className="appearance-workspace-preview__nav">
        <SidebarHeader><strong>DBFox</strong></SidebarHeader>
        <SidebarContent>
          <SidebarNavRow icon={<Plus />} label="新任务" active />
          <SidebarNavRow icon={<Folder />} label="项目" />
        </SidebarContent>
      </Sidebar>
      <div className="appearance-workspace-preview__main">
        <strong>订单趋势分析</strong>
        <p>分析已完成，找到 18 条符合条件的记录。</p>
        <ReferenceCard name="每周报告.xlsx" kind="spreadsheet" />
        <div className="appearance-workspace-preview__table"><table><thead><tr><th>id</th><th>状态</th><th>金额</th></tr></thead>
          <tbody><tr><td>1024</td><td>已完成</td><td>¥ 328</td></tr></tbody></table></div>
        <code>SELECT * FROM orders;</code>
        <UnifiedComposer value="" onChange={() => {}} onSubmit={() => {}} onAddAttachment={() => {}}
          placeholder="输入你的问题…" ariaLabel="预览输入框" compact />
      </div>
    </div>
  </aside>;
}
