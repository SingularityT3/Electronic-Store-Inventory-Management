import { useState, type FormEvent } from 'react';

export default function SearchBox({
  value = '',
  onSearch,
  label = 'Search products',
}: {
  value?: string;
  onSearch: (value: string) => void;
  label?: string;
}) {
  const [term, setTerm] = useState(value);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSearch(term.trim());
  }

  function clear() {
    setTerm('');
    onSearch('');
  }

  return (
    <form role="search" onSubmit={submit} className="search-box">
      <label htmlFor="product-search">{label}</label>
      <input
        id="product-search"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        type="search"
      />
      <button type="submit">Search</button>
      <button type="button" onClick={clear} disabled={!term}>
        Clear
      </button>
    </form>
  );
}
