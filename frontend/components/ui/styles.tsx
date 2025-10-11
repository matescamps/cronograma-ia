import styled from 'styled-components';

export const Button = styled.button`
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  font-weight: 500;
  transition: all 0.2s;
  cursor: pointer;

  &.primary {
    background-color: var(--primary-color);
    color: white;
    border: none;

    &:hover {
      opacity: 0.9;
    }
  }

  &.secondary {
    background-color: transparent;
    border: 1px solid var(--panel-color);
    color: var(--secondary-color);

    &:hover {
      border-color: var(--primary-color);
      color: var(--primary-color);
    }
  }
`;

export const Card = styled.div`
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 1rem;
  padding: 1.5rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);

  [data-theme='dark'] & {
    background: rgba(0, 0, 0, 0.3);
  }
`;

export const Input = styled.input`
  width: 100%;
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid var(--panel-color);
  background-color: var(--surface-color);
  color: var(--secondary-color);
  transition: all 0.2s;

  &:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 2px var(--primary-color-20);
  }
`;

export const Heading = styled.h1`
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 1rem;
  color: var(--secondary-color);
`;

export const Text = styled.p`
  color: var(--muted-color);
  line-height: 1.6;
`;

export const Grid = styled.div`
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
`;

export const Flex = styled.div`
  display: flex;
  gap: 1rem;
  align-items: center;

  &.between {
    justify-content: space-between;
  }

  &.center {
    justify-content: center;
  }
`;

export const Badge = styled.span`
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
  background-color: var(--panel-color);
  color: var(--secondary-color);

  &.success {
    background-color: var(--success-color);
    color: white;
  }

  &.primary {
    background-color: var(--primary-color);
    color: white;
  }
`;