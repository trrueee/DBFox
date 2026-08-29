import { useState, type FormEvent } from "react";
import { AlertCircle, FolderPlus } from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  ErrorDetails,
  Field,
  FieldLabel,
  Input,
} from "../../components/ui";
import { useProjectState } from "./useProjectState";
import { getUserErrorMessage } from "../../lib/api/client";
import "./ProjectCreateForm.css";

interface ProjectCreateFormProps {
  onCreated: (projectId: string) => void;
  onCancel: () => void;
}

export function ProjectCreateForm({ onCreated, onCancel }: ProjectCreateFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [submitError, setSubmitError] = useState<unknown | null>(null);
  const { createProject } = useProjectState("");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setValidationError("项目名称不能为空。");
      return;
    }
    setSubmitting(true);
    setValidationError("");
    setSubmitError(null);
    try {
      const project = await createProject({
        name: trimmedName,
        description: description.trim() || null,
      });
      onCreated(project.id);
    } catch (submitError) {
      setSubmitError(submitError);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="project-create__form" onSubmit={(event) => void handleSubmit(event)}>
      <Field className="project-create__field" data-invalid={Boolean(validationError)}>
        <FieldLabel htmlFor="project-create-name" className="project-create__label">项目名称</FieldLabel>
        <Input
          id="project-create-name"
          autoFocus
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            if (validationError) setValidationError("");
          }}
          placeholder="例如：电商经营分析"
          maxLength={128}
          disabled={submitting}
          aria-invalid={Boolean(validationError)}
        />
      </Field>
      <Field className="project-create__field">
        <FieldLabel htmlFor="project-create-description" className="project-create__label">项目描述（可选）</FieldLabel>
        <Input
          id="project-create-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="这个项目主要分析什么？"
          maxLength={2_000}
          disabled={submitting}
        />
      </Field>
      {validationError ? (
        <Alert className="project-create__error" variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      ) : submitError ? (
        <Alert className="project-create__error" variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>创建项目失败</AlertTitle>
          <AlertDescription>
            <p>{getUserErrorMessage(submitError, "创建项目失败，请重试。")}</p>
            <ErrorDetails error={submitError} />
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="project-create__actions">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
        <Button type="submit" disabled={submitting}>
          <FolderPlus size={14} aria-hidden="true" />
          {submitting ? "正在创建…" : "创建项目"}
        </Button>
      </div>
    </form>
  );
}
