interface UserPromptCardProps {
  queryText: string;
  createdAt?: number;
}

export function UserPromptCard({ queryText }: UserPromptCardProps) {
  if (!queryText.trim()) return null;

  return (
    <div className="task-user-prompt animate-fade-up">
      <div className="task-prompt-text">{queryText}</div>
    </div>
  );
}
