program ScalarOverflow;

function AddSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left + Right;
end;

function AddUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left + Right;
end;

begin
  Writeln('SignedOverflow=', AddSigned(High(Integer), 1));
  Writeln('UnsignedOverflow=', AddUnsigned(High(Cardinal), 1));
end.
