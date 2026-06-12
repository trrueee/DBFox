import * as React from "react";

interface SelectProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  placeholder?: string;
}

function Select({ value, onValueChange, children, placeholder }: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      className="flex h-8 w-full rounded-[var(--radius)] border border-[hsl(var(--input))] bg-transparent px-3 py-1 text-sm transition-all duration-150 hover:border-[hsl(var(--primary)/0.3)] focus-visible:outline-none focus-visible:border-[hsl(var(--primary)/0.5)] focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.1)] disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer appearance-none"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 8px center",
        paddingRight: "28px",
      }}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {children}
    </select>
  );
}

interface SelectItemProps {
  value: string;
  children: React.ReactNode;
}

function SelectItem({ value, children }: SelectItemProps) {
  return <option value={value}>{children}</option>;
}

export { Select, SelectItem };
