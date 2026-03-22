function Header() {
  return (
    <header className="text-center py-8 px-4">
      <h1 className="text-4xl font-bold text-gray-900 mb-3">
        ID Document Scanner
      </h1>
      <p className="text-lg text-gray-600 mb-2">
        Upload an ID card or passport image to extract document information
      </p>
      <p className="text-sm text-gray-400">
        Supported formats: JPEG, PNG, BMP, TIFF, WebP
      </p>
    </header>
  );
}

export default Header;
