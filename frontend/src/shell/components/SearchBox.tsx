import { useEffect, useRef, useState, type FormEvent, type Ref } from 'react';

export default function SearchBox({
  value = '',
  onSearch,
  label = 'Search products',
  autoFocus = false,
  inputRef,
  resetKey = 0,
}: {
  value?: string;
  onSearch: (value: string) => void;
  label?: string;
  autoFocus?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  resetKey?: number;
}) {
  const [term, setTerm] = useState(value);
  const fallbackRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTerm(value);
  }, [value]);

  useEffect(() => {
    if (resetKey > 0) setTerm(value);
  }, [resetKey, value]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSearch(term.trim());
  }

  function clear() {
    setTerm('');
    onSearch('');
  }

  return (
    <form
      role="search"
      onSubmit={submit}
      className="search-box"
      onKeyDown={(event) => {
        if (event.key === 'Escape') clear();
      }}
    >
      <label htmlFor="product-search">{label}</label>
      <input
        id="product-search"
        ref={inputRef ?? fallbackRef}
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        type="search"
        autoFocus={autoFocus}
      />
      <button type="submit">Search</button>
      <button type="button" onClick={clear} disabled={!term}>
        Clear
      </button>
    </form>
  );
}
