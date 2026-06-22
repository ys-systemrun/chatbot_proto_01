import type { Meta, StoryObj } from '@storybook/react'
import InputBar from './InputBar'

const meta = {
  component: InputBar,
  title: 'Components/InputBar',
  args: {
    onSubmit: (text: string) => console.log('submitted:', text),
  },
} satisfies Meta<typeof InputBar>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: { disabled: false },
}

export const Disabled: Story = {
  args: { disabled: true },
}
