import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "../../lib/utils";
import "./select.css";

type SelectChangeEvent = {
  target: { value: string };
  currentTarget: { value: string };
};

type SelectProps = Omit<
  React.ButtonHTMLAttributes<HTMLButtonElement>,
  "children" | "defaultValue" | "onChange" | "value"
> & {
  children: React.ReactNode;
  defaultValue?: string | number;
  name?: string;
  onChange?: (event: SelectChangeEvent) => void;
  required?: boolean;
  value?: string | number;
};

interface SelectOption {
  disabled?: boolean;
  label: React.ReactNode;
  textValue: string;
  value: string;
}

const Select = React.forwardRef<HTMLButtonElement, SelectProps>(
  (
    {
      children,
      className,
      defaultValue,
      disabled,
      id,
      name,
      onChange,
      required,
      value,
      ...props
    },
    ref,
  ) => {
    const options = React.useMemo(() => getSelectOptions(children), [children]);
    const handleValueChange = React.useCallback(
      (nextValue: string) => {
        onChange?.({ target: { value: nextValue }, currentTarget: { value: nextValue } });
      },
      [onChange],
    );

    return (
      <SelectPrimitive.Root
        defaultValue={defaultValue === undefined ? undefined : String(defaultValue)}
        disabled={disabled}
        name={name}
        onValueChange={handleValueChange}
        required={required}
        value={value === undefined ? undefined : String(value)}
      >
        <SelectPrimitive.Trigger
          ref={ref}
          id={id}
          className={cn("dbfox-select-trigger", className)}
          {...props}
        >
          <SelectPrimitive.Value />
          <SelectPrimitive.Icon asChild>
            <ChevronDown className="dbfox-select-icon" aria-hidden="true" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="dbfox-select-content" position="popper" sideOffset={4}>
            <SelectPrimitive.ScrollUpButton className="dbfox-select-scroll-button">
              <ChevronUp size={12} aria-hidden="true" />
            </SelectPrimitive.ScrollUpButton>
            <SelectPrimitive.Viewport className="dbfox-select-viewport">
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  className="dbfox-select-item"
                  disabled={option.disabled}
                  textValue={option.textValue}
                  value={option.value}
                >
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="dbfox-select-item-indicator">
                    <Check size={12} aria-hidden="true" />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
            <SelectPrimitive.ScrollDownButton className="dbfox-select-scroll-button">
              <ChevronDown size={12} aria-hidden="true" />
            </SelectPrimitive.ScrollDownButton>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    );
  },
);
Select.displayName = "Select";

function getSelectOptions(children: React.ReactNode): SelectOption[] {
  return React.Children.toArray(children).flatMap((child) => {
    if (!React.isValidElement<React.OptionHTMLAttributes<HTMLOptionElement>>(child)) return [];
    const props = child.props;
    const value = props.value === undefined ? nodeToText(props.children) : String(props.value);
    if (!value) return [];
    return [{
      disabled: props.disabled,
      label: props.children,
      textValue: nodeToText(props.children),
      value,
    }];
  });
}

function nodeToText(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join("");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return nodeToText(node.props.children);
  return "";
}

export { Select };
