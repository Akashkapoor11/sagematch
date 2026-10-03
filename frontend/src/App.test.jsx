import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import App from './App.jsx'

describe('SageMatch React shell', () => {
  it('renders the product-facing decision engine shell', () => {
    const html = renderToStaticMarkup(<App />)
    expect(html).toContain('SageMatch')
    expect(html).toContain('Analyze requirements')
    expect(html).toContain('Data quality')
    expect(html).toContain('TOP 3')
  })
})
