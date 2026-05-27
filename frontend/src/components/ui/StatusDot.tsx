export function StatusDot({
    status,
    pulse = false,
}: {
    status: 'green' | 'amber' | 'red' | 'gray'
    pulse?: boolean
}) {
    const colours = {
        green: 'bg-green-500',
        amber: 'bg-amber-500',
        red: 'bg-red-500',
        gray: 'bg-gray-600',
    }
    return (
        <span className="relative flex h-2.5 w-2.5">
            {pulse && (
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${colours[status]} opacity-75`} />
            )}
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${colours[status]}`} />
        </span>
    )
}